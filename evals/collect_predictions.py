"""Call the live chat API and record real RAG responses for evaluation."""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas import AnswerEvaluationRecord, AnswerEvaluationScenario


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSONL answer scenarios")
    parser.add_argument("--output", type=Path, required=True, help="JSONL recorded live responses")
    parser.add_argument("--api-base-url", default="http://localhost:8000", help="Chat API base URL")
    parser.add_argument(
        "--api-key-env",
        default="DEMO_API_KEY",
        help="Environment variable holding the API Key; never writes it to a file",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout")
    return parser.parse_args()


def load_scenarios(input_path: Path) -> list[AnswerEvaluationScenario]:
    scenarios: list[AnswerEvaluationScenario] = []
    for line_number, line in enumerate(
        input_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            scenarios.append(AnswerEvaluationScenario.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"invalid evaluation scenario on line {line_number}") from exc
    if not scenarios:
        raise ValueError("evaluation scenario input must contain at least one record")
    if len({scenario.id for scenario in scenarios}) != len(scenarios):
        raise ValueError("evaluation scenario ids must be unique")
    return scenarios


def request_json(
    base_url: str,
    path: str,
    api_key: str,
    body: dict[str, Any] | None,
    timeout_seconds: float,
) -> tuple[dict[str, Any], int]:
    """Make one authenticated request while exposing no response body on failure."""
    content = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"X-API-Key": api_key}
    if content is not None:
        headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=content,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - caller controls URL.
            response_body = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"API returned HTTP {exc.code} for {path}") from exc
    except URLError as exc:
        raise RuntimeError(f"API connection failed for {path}") from exc
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API returned invalid JSON for {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"API returned an invalid object for {path}")
    return payload, int((time.perf_counter() - started) * 1000)


def collect(
    input_path: Path,
    output_path: Path,
    api_base_url: str,
    api_key: str,
    timeout_seconds: float,
) -> list[AnswerEvaluationRecord]:
    """Collect answer records sequentially so conversation and latency stay attributable."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    scenarios = load_scenarios(input_path)
    identity, _ = request_json(api_base_url, "/api/v1/users/me", api_key, None, timeout_seconds)
    user_id = identity.get("user_id")
    if not isinstance(user_id, str):
        raise RuntimeError("API identity response does not contain user_id")

    records: list[AnswerEvaluationRecord] = []
    for scenario in scenarios:
        conversation, _ = request_json(
            api_base_url,
            "/api/v1/conversations",
            api_key,
            {"user_id": user_id, "title": f"评测：{scenario.id}"},
            timeout_seconds,
        )
        conversation_id = conversation.get("conversation_id")
        if not isinstance(conversation_id, str):
            raise RuntimeError("API conversation response does not contain conversation_id")
        chat, observed_latency_ms = request_json(
            api_base_url,
            "/api/v1/chat",
            api_key,
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "query": scenario.question,
            },
            timeout_seconds,
        )
        records.append(
            AnswerEvaluationRecord.model_validate(
                {
                    "id": scenario.id,
                    "kind": "answer",
                    "question": scenario.question,
                    "expected_answer": scenario.expected_answer,
                    "expected_source": scenario.expected_source,
                    "prediction": chat.get("answer", ""),
                    "predicted_sources": chat.get("sources", []),
                    "latency_ms": chat.get("latency_ms"),
                    "observed_latency_ms": observed_latency_ms,
                }
            )
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(record.model_dump_json() for record in records) + "\n",
        encoding="utf-8",
    )
    return records


if __name__ == "__main__":
    arguments = parse_arguments()
    api_key = os.environ.get(arguments.api_key_env)
    if not api_key:
        raise SystemExit(f"environment variable {arguments.api_key_env} is required")
    collect(
        arguments.input,
        arguments.output,
        arguments.api_base_url,
        api_key,
        arguments.timeout_seconds,
    )
