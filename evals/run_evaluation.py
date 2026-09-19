"""Evaluate recorded real responses and generate JSON plus Markdown reports."""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from app.schemas import (
    AnswerEvaluationRecord,
    AnswerEvaluationResult,
    ToolEvaluationRecord,
    ToolEvaluationResult,
)
from app.services.evaluation import (
    average_metrics,
    evaluate_answer,
    evaluate_tool,
    latency_summary,
)
from app.services.llm import LlmClient

EvaluationRecord = AnswerEvaluationRecord | ToolEvaluationRecord
record_adapter: TypeAdapter[EvaluationRecord] = TypeAdapter(EvaluationRecord)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSONL recorded predictions")
    parser.add_argument("--output", type=Path, required=True, help="JSON metrics report")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        help="Optional Markdown report path; defaults beside --output",
    )
    return parser.parse_args()


def load_records(input_path: Path) -> list[EvaluationRecord]:
    """Validate each JSONL line before sending any content to the evaluation model."""
    records: list[EvaluationRecord] = []
    for line_number, line in enumerate(
        input_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(record_adapter.validate_json(line))
        except Exception as exc:
            raise ValueError(f"invalid evaluation record on line {line_number}") from exc
    if not records:
        raise ValueError("evaluation input must contain at least one record")
    if len({record.id for record in records}) != len(records):
        raise ValueError("evaluation record ids must be unique")
    return records


def markdown_report(report: dict[str, Any]) -> str:
    """Render a portable review report without embedding full customer answers."""
    metrics = report["metrics"]
    latency = report["latency"]
    lines = [
        "# 评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 输入文件：`{report['input_file']}`",
        f"- 有效用例：{report['count']}",
        "",
        "## 质量指标",
        "",
        "| 指标 | 分数 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {name} | {value} |" for name, value in sorted(metrics.items()))
    lines.extend(
        [
            "",
            "## 耗时统计（ms）",
            "",
            "| 类型 | 样本数 | 最小 | 平均 | P50 | P95 | 最大 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, values in latency.items():
        if not values:
            continue
        lines.append(
            "| {name} | {count} | {min_ms} | {mean_ms} | {p50_ms} | {p95_ms} | {max_ms} |".format(
                name=name,
                **values,
            )
        )
    lines.extend(
        [
            "",
            "## 用例明细",
            "",
            "| 用例 | 类型 | 服务端耗时 | 端到端耗时 | 评测耗时 | 评分摘要 | 评分说明 |",
            "| --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for result in report["results"]:
        scores = ", ".join(f"{key}={value}" for key, value in result["scores"].items())
        observed_latency_ms = result["observed_latency_ms"]
        lines.append(
            (
                "| {id} | {kind} | {latency_ms} | {observed_latency_ms} | "
                "{judge_latency_ms} | {scores} | {reason} |"
            ).format(
                id=result["id"],
                kind=result["kind"],
                latency_ms=result["latency_ms"],
                observed_latency_ms=(
                    observed_latency_ms if observed_latency_ms is not None else "-"
                ),
                judge_latency_ms=result["judge_latency_ms"],
                scores=scores.replace("|", "/"),
                reason=result["reason"].replace("|", "/").replace("\n", " "),
            )
        )
    return "\n".join(lines) + "\n"


async def run(
    input_path: Path, output_path: Path, markdown_output: Path | None = None
) -> dict[str, Any]:
    records = load_records(input_path)
    llm = LlmClient()
    results: list[dict[str, Any]] = []
    for record in records:
        started = time.perf_counter()
        payload = record.model_dump(mode="json")
        result: AnswerEvaluationResult | ToolEvaluationResult
        if record.kind == "answer":
            result = await evaluate_answer(payload, llm)
        elif record.kind == "tool":
            result = await evaluate_tool(payload, llm)
        else:
            raise AssertionError("unreachable")
        scores = result.model_dump(exclude={"reason"})
        results.append(
            {
                "id": record.id,
                "kind": record.kind,
                "latency_ms": record.latency_ms,
                "observed_latency_ms": record.observed_latency_ms,
                "judge_latency_ms": int((time.perf_counter() - started) * 1000),
                "scores": scores,
                "reason": result.reason,
            }
        )
    report = {
        "schema_version": "v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "input_file": input_path.name,
        "count": len(results),
        "metrics": average_metrics([result["scores"] for result in results]),
        "latency": {
            "server": latency_summary(record.latency_ms for record in records),
            "end_to_end": latency_summary(
                record.observed_latency_ms
                for record in records
                if record.observed_latency_ms is not None
            ),
            "evaluator": latency_summary(result["judge_latency_ms"] for result in results),
        },
        "judge_usage": {
            "prompt_tokens": llm.prompt_tokens,
            "completion_tokens": llm.completion_tokens,
        },
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = markdown_output or output_path.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    return report


if __name__ == "__main__":
    arguments = parse_arguments()
    asyncio.run(run(arguments.input, arguments.output, arguments.markdown_output))
