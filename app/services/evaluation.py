"""Structured LLM evaluation, metrics, and latency summaries for real test runs."""

import math
from collections.abc import Iterable
from typing import Any

from app.prompts import EVALUATE_ANSWER_PROMPT_V1, EVALUATE_TOOL_PROMPT_V1
from app.schemas import AnswerEvaluationResult, ToolEvaluationResult
from app.services.llm import LlmClient, compact_json


async def evaluate_answer(record: dict[str, Any], llm: LlmClient) -> AnswerEvaluationResult:
    return await llm.structured(
        EVALUATE_ANSWER_PROMPT_V1.format(
            question=record["question"],
            expected_answer=record["expected_answer"],
            expected_source=record["expected_source"],
            prediction=record["prediction"],
            predicted_sources=compact_json(record["predicted_sources"]),
        ),
        AnswerEvaluationResult,
    )


async def evaluate_tool(record: dict[str, Any], llm: LlmClient) -> ToolEvaluationResult:
    return await llm.structured(
        EVALUATE_TOOL_PROMPT_V1.format(
            question=record["question"],
            expected_tool=record["expected_tool"],
            expected_input=compact_json(record["expected_input"]),
            predicted_tool=record["predicted_tool"],
            predicted_input=compact_json(record["predicted_input"]),
        ),
        ToolEvaluationResult,
    )


def average_metrics(results: Iterable[dict[str, float]]) -> dict[str, float]:
    rows = list(results)
    if not rows:
        return {}
    keys = {
        key
        for row in rows
        for key, value in row.items()
        if key != "hallucination" and isinstance(value, (int, float))
    }
    metrics = {
        key: round(
            sum(float(row[key]) for row in rows if isinstance(row.get(key), (int, float)))
            / sum(1 for row in rows if isinstance(row.get(key), (int, float))),
            4,
        )
        for key in keys
    }
    hallucinations = [row["hallucination"] for row in rows if "hallucination" in row]
    if hallucinations:
        metrics["hallucination_rate"] = round(sum(hallucinations) / len(hallucinations), 4)
    return metrics


def latency_summary(latencies: Iterable[int]) -> dict[str, float | int]:
    """Return deterministic nearest-rank latency statistics in milliseconds."""
    values = sorted(latencies)
    if not values:
        return {}

    def percentile(percent: float) -> int:
        index = max(0, math.ceil(percent * len(values)) - 1)
        return values[index]

    return {
        "count": len(values),
        "min_ms": values[0],
        "mean_ms": round(sum(values) / len(values), 2),
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "max_ms": values[-1],
    }
