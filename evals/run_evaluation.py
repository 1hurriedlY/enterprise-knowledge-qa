"""Evaluate recorded RAG and tool responses, then write reproducible metrics."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.services.evaluation import average_metrics, evaluate_answer, evaluate_tool
from app.services.llm import LlmClient


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSONL recorded predictions")
    parser.add_argument("--output", type=Path, required=True, help="JSON metrics report")
    return parser.parse_args()


async def run(input_path: Path, output_path: Path) -> None:
    records = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line]
    llm = LlmClient()
    results: list[dict[str, Any]] = []
    for record in records:
        if record["kind"] == "answer":
            result = await evaluate_answer(record, llm)
        elif record["kind"] == "tool":
            result = await evaluate_tool(record, llm)
        else:
            raise ValueError(f"unsupported evaluation kind: {record['kind']}")
        results.append({"id": record["id"], "kind": record["kind"], **result.model_dump()})
    report = {"count": len(results), "metrics": average_metrics(results), "results": results}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    arguments = parse_arguments()
    asyncio.run(run(arguments.input, arguments.output))
