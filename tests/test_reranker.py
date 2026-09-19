import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import RagAnswerResult, SourceCitation
from app.services import chat
from app.services.reranker import RerankClient, RerankError, RerankScore, parse_rerank_scores


def test_parse_rerank_scores_accepts_cohere_fields() -> None:
    scores = parse_rerank_scores(
        {"results": [{"index": 1, "relevance_score": 0.91}, {"index": 0, "score": 0.42}]},
        2,
    )

    assert scores == [RerankScore(index=1, score=0.91), RerankScore(index=0, score=0.42)]


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [{"index": 2, "score": 0.5}]},
        {"results": [{"index": True, "score": 0.5}]},
        {"results": [{"index": 0, "score": 1.1}]},
        {"results": [{"index": 0, "score": 0.5}, {"index": 0, "score": 0.4}]},
    ],
)
def test_parse_rerank_scores_rejects_invalid_results(payload: object) -> None:
    with pytest.raises(RerankError):
        parse_rerank_scores(payload, 2)


def _chunk(score: float, content: str) -> chat.RetrievedChunk:
    source = SourceCitation(
        document_id=uuid.uuid4(),
        filename="guide.md",
        chunk_id=uuid.uuid4(),
        heading_path="退款",
        content=content,
        score=score,
    )
    return chat.RetrievedChunk(number="", source=source)


def test_apply_rerank_sorts_filters_and_renumbers() -> None:
    candidates = [_chunk(0.8, "A"), _chunk(0.7, "B"), _chunk(0.6, "C")]

    result = chat._apply_rerank(
        candidates,
        [RerankScore(index=2, score=0.95), RerankScore(index=0, score=0.25)],
        score_threshold=0.30,
    )

    assert [(item.number, item.source.content, item.source.score) for item in result] == [
        ("1", "C", 0.95)
    ]


def test_validated_rag_answer_discards_unknown_citations() -> None:
    retrieved = chat._renumber_chunks([_chunk(0.8, "退款政策")])
    result = RagAnswerResult(
        answer="依据 [1]，并且不应出现 [2]。",
        citations=["1", "2"],
        confidence="high",
        need_human=False,
    )

    answer, sources, need_human = chat._validated_rag_answer(result, retrieved)

    assert answer == "依据 [1]，并且不应出现 。"
    assert len(sources) == 1
    assert need_human is False


@pytest.mark.asyncio
async def test_rerank_failure_falls_back_to_vector_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [_chunk(0.8, "A"), _chunk(0.7, "B")]

    class FailingRerankClient:
        def __init__(self, settings: object) -> None:
            del settings

        async def rerank(self, query: str, documents: list[str], top_n: int) -> list[RerankScore]:
            del query, documents, top_n
            raise RerankError("unavailable")

    settings = SimpleNamespace(
        retrieval_score_threshold=0.3,
        rerank_enabled=True,
        rerank_top_n=5,
        rerank_score_threshold=0.3,
    )
    monkeypatch.setattr(chat, "RerankClient", FailingRerankClient)

    result = await chat._rerank_candidates("退款", candidates, settings)

    assert [(item.number, item.source.content) for item in result] == [("1", "A"), ("2", "B")]


@pytest.mark.asyncio
async def test_disabled_rerank_does_not_call_provider() -> None:
    settings = SimpleNamespace(rerank_enabled=False)
    client = RerankClient(settings)  # type: ignore[arg-type]

    assert await client.rerank("退款", ["政策内容"]) == []


def test_enabled_rerank_requires_model() -> None:
    with pytest.raises(ValidationError, match="RERANK_MODEL"):
        Settings.model_validate(
            {
                "database_url": "postgresql+asyncpg://user:pass@localhost/db",
                "redis_url": "redis://localhost:6379/0",
                "qdrant_url": "http://localhost:6333",
                "llm_base_url": "https://example.com/v1",
                "llm_api_key": "test-key",
                "chat_model": "chat",
                "embedding_model": "embedding",
                "embedding_dimension": 3,
                "demo_api_key": "demo-key",
                "rerank_enabled": True,
            }
        )
