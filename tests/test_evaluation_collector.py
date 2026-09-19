import json
from pathlib import Path

import pytest

from evals import collect_predictions


def test_collector_requires_valid_scenarios(tmp_path: Path) -> None:
    path = tmp_path / "scenarios.jsonl"
    path.write_text('{"id":"bad","question":"退款？"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        collect_predictions.load_scenarios(path)


def test_collector_records_live_response_and_both_latencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "scenarios.jsonl"
    output_path = tmp_path / "predictions.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "id": "refund_process",
                "question": "如何申请退款？",
                "expected_answer": "在订单详情页申请退款。",
                "expected_source": "退款政策.md#退款流程",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    responses = iter(
        [
            ({"user_id": "c76c755d-4580-42fc-9b50-4033d001af72"}, 3),
            ({"conversation_id": "f2f76c75-4580-42fc-9b50-4033d001af72"}, 4),
            ({"answer": "请在订单详情页申请退款。", "sources": [], "latency_ms": 21}, 25),
        ]
    )

    def fake_request_json(*_: object) -> tuple[dict[str, object], int]:
        return next(responses)

    monkeypatch.setattr(collect_predictions, "request_json", fake_request_json)

    records = collect_predictions.collect(
        input_path, output_path, "http://api.example", "test-key", 30.0
    )

    assert records[0].latency_ms == 21
    assert records[0].observed_latency_ms == 25
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["prediction"] == "请在订单详情页申请退款。"
