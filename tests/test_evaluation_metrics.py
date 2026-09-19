from app.services.evaluation import average_metrics


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
