import json
from pathlib import Path


def test_evaluation_set_covers_prd_acceptance_categories() -> None:
    path = Path("evals/cases.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["version"] == "v1"
    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    assert {"ingestion", "rag", "tools", "safety", "security"} <= {
        case["category"] for case in cases
    }
    assert all({"id", "category", "input", "expected"} <= case.keys() for case in cases)
