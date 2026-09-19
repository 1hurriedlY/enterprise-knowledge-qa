from app.services.evaluation import average_metrics, latency_summary


def test_average_metrics_reports_answer_and_tool_scores() -> None:
    metrics = average_metrics(
        [
            {
                "correctness": 1.0,
                "source_correctness": 1.0,
                "hallucination": 0.0,
                "completeness": 0.5,
            },
            {
                "tool_correct": 1.0,
                "arguments_correct": 0.5,
            },
        ]
    )

    assert metrics == {
        "correctness": 1.0,
        "source_correctness": 1.0,
        "completeness": 0.5,
        "tool_correct": 1.0,
        "arguments_correct": 0.5,
        "hallucination_rate": 0.0,
    }


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    assert latency_summary([10, 20, 30, 40, 50]) == {
        "count": 5,
        "min_ms": 10,
        "mean_ms": 30.0,
        "p50_ms": 30,
        "p95_ms": 50,
        "max_ms": 50,
    }
    assert latency_summary([]) == {}
