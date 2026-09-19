import uuid
from types import SimpleNamespace

import pytest

from app.models import Chunk, Document
from app.services import chat
from app.services.bm25 import Bm25Hit, search, tokenize


def test_tokenize_handles_chinese_and_ascii_terms() -> None:
    assert tokenize("退款 policy-2026") == ["退", "款", "policy", "2026"]


def test_bm25_prefers_exact_terms_and_limits_results() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    third = uuid.uuid4()

    hits = search(
        "订单号 A2026",
        [
            (first, "订单号 A2026 的物流状态"),
            (second, "订单状态查询说明"),
            (third, "退款政策和申请流程"),
        ],
        limit=2,
    )

    assert [hit.chunk_id for hit in hits] == [first, second]
    assert hits[0].score > hits[1].score


def test_hybrid_fusion_can_promote_keyword_match() -> None:
    semantic = uuid.uuid4()
    keyword = uuid.uuid4()

    hits = chat._fuse_hybrid_hits(
        [(semantic, 0.9), (keyword, 0.5)],
        [Bm25Hit(chunk_id=keyword, score=5.0)],
        vector_weight=0.6,
        bm25_weight=0.4,
        limit=2,
    )

    assert [chunk_id for chunk_id, _ in hits] == [keyword, semantic]
    assert all(0 <= score <= 1 for _, score in hits)


def test_hybrid_fusion_handles_empty_bm25_results() -> None:
    vector_id = uuid.uuid4()

    hits = chat._fuse_hybrid_hits(
        [(vector_id, 0.8)], [], vector_weight=0.6, bm25_weight=0.4, limit=10
    )

    assert hits == [(vector_id, 0.48)]


@pytest.mark.asyncio
async def test_retrieve_uses_keyword_and_vector_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    semantic_id = uuid.uuid4()
    keyword_id = uuid.uuid4()
    document = Document(
        id=document_id,
        user_id=user_id,
        filename="orders.md",
        file_type="md",
        file_path="/tmp/orders.md",
        file_size=10,
        content_hash="a" * 64,
    )
    semantic_chunk = Chunk(
        id=semantic_id,
        document_id=document_id,
        content="订单状态查询说明",
        heading_path="订单",
        chunk_index=0,
        vector_point_id=str(uuid.uuid4()),
    )
    keyword_chunk = Chunk(
        id=keyword_id,
        document_id=document_id,
        content="订单号 A2026 的物流状态",
        heading_path="物流",
        chunk_index=1,
        vector_point_id=str(uuid.uuid4()),
    )

    class FakeSession:
        async def execute(self, _: object) -> SimpleNamespace:
            return SimpleNamespace(
                all=lambda: [(semantic_chunk, document), (keyword_chunk, document)],
                one=lambda: (2, None),
            )

    class FakeLlm:
        async def embed(self, _: str) -> list[float]:
            return [0.1]

    class FakeVectorStore:
        async def search(
            self, _: uuid.UUID, __: list[float], limit: int
        ) -> list[tuple[uuid.UUID, float]]:
            assert limit == 10
            return [(semantic_id, 0.5)]

    settings = SimpleNamespace(
        retrieval_score_threshold=0.3,
        hybrid_search_enabled=True,
        hybrid_vector_weight=0.6,
        hybrid_bm25_weight=0.4,
        bm25_cache_ttl_seconds=60,
        bm25_cache_max_users=100,
        bm25_cache_max_chunks=10000,
        rerank_enabled=False,
    )
    monkeypatch.setattr(chat, "get_settings", lambda: settings)
    monkeypatch.setattr(chat, "VectorStore", FakeVectorStore)

    result = await chat._retrieve(FakeSession(), user_id, "订单号 A2026", FakeLlm())

    assert [item.source.chunk_id for item in result] == [keyword_id, semantic_id]

    class EmptyVectorStore:
        async def search(
            self, _: uuid.UUID, __: list[float], limit: int
        ) -> list[tuple[uuid.UUID, float]]:
            assert limit == 10
            return []

    monkeypatch.setattr(chat, "VectorStore", EmptyVectorStore)
    bm25_only = await chat._retrieve(FakeSession(), user_id, "订单号 A2026", FakeLlm())

    assert [item.source.chunk_id for item in bm25_only] == [keyword_id]

    class VectorFallbackStore:
        async def search(
            self, _: uuid.UUID, __: list[float], limit: int
        ) -> list[tuple[uuid.UUID, float]]:
            assert limit == 10
            return [(semantic_id, 0.5)]

    settings.bm25_cache_max_chunks = 1
    monkeypatch.setattr(chat, "VectorStore", VectorFallbackStore)
    oversized = await chat._retrieve(FakeSession(), user_id, "订单号 A2026", FakeLlm())

    assert [item.source.chunk_id for item in oversized] == [semantic_id]
