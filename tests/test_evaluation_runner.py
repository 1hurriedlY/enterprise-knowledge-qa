import json
from pathlib import Path

import pytest

from app.schemas import AnswerEvaluationResult, ToolEvaluationResult
from evals import run_evaluation


def _write_records(path: Path) -> None:
    records = [
        {
            "id": "refund_answer",
            "kind": "answer",
            "question": "如何申请退款？",
            "expected_answer": "在订单详情页申请退款。",
            "expected_source": "退款政策.md#退款流程",
            "prediction": "请在订单详情页申请退款。[1]",
            "predicted_sources": [],
            "latency_ms": 120,
            "observed_latency_ms": 140,
        },
        {
            "id": "order_tool",
            "kind": "tool",
            "question": "订单 12345 发货了吗？",
            "expected_tool": "query_order",
            "expected_input": {"order_id": "12345"},
            "predicted_tool": "query_order",
            "predicted_input": {"order_id": "12345"},
            "latency_ms": 80,
        },
    ]
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8"
    )


def test_load_records_requires_real_latency_and_unique_ids(tmp_path: Path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "missing_latency",
                "kind": "answer",
                "question": "退款？",
                "expected_answer": "申请退款。",
                "expected_source": "政策.md",
                "prediction": "申请退款。",
                "predicted_sources": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 1"):
        run_evaluation.load_records(path)


@pytest.mark.asyncio
async def test_runner_writes_json_and_markdown_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "predictions.jsonl"
    output_path = tmp_path / "report.json"
    _write_records(input_path)

    class FakeLlm:
        prompt_tokens = 17
        completion_tokens = 9

    async def fake_answer(_: dict[str, object], __: FakeLlm) -> AnswerEvaluationResult:
        return AnswerEvaluationResult(
            correctness=1,
            source_correctness=1,
            hallucination=0,
            completeness=1,
            reason="回答与来源正确",
        )

    async def fake_tool(_: dict[str, object], __: FakeLlm) -> ToolEvaluationResult:
        return ToolEvaluationResult(
            tool_correct=1,
            arguments_correct=1,
            reason="工具与参数正确",
        )

    monkeypatch.setattr(run_evaluation, "LlmClient", FakeLlm)
    monkeypatch.setattr(run_evaluation, "evaluate_answer", fake_answer)
    monkeypatch.setattr(run_evaluation, "evaluate_tool", fake_tool)

    report = await run_evaluation.run(input_path, output_path)

    assert report["metrics"]["correctness"] == 1.0
    assert report["latency"]["server"]["p95_ms"] == 120
    assert report["latency"]["end_to_end"]["mean_ms"] == 140.0
    assert report["judge_usage"] == {"prompt_tokens": 17, "completion_tokens": 9}
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema_version"] == "v2"
    markdown = output_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "# 评测报告" in markdown
    assert "refund_answer" in markdown
