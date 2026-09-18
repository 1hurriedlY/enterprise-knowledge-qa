import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.models import Embedding
from app.services.ingestion import get_or_create_embeddings
from app.services.vector_store import VectorPoint, VectorStore


class FakeVectorClient:
    def __init__(self) -> None:
        self.query_kwargs: dict[str, object] | None = None
        self.upserted: list[object] = []

    async def collection_exists(self, _: str) -> bool:
        return True

    async def query_points(self, **kwargs: object) -> SimpleNamespace:
        self.query_kwargs = kwargs
        return SimpleNamespace(points=[])

    async def upsert(self, **kwargs: object) -> None:
        self.upserted = kwargs["points"]  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_search_always_filters_by_user_and_caps_top_k() -> None:
    store = VectorStore()
    client = FakeVectorClient()
    store.client = client  # type: ignore[assignment]
    user_id = uuid.uuid4()

    await store.search(user_id, [0.1] * 1024, limit=99)

    assert client.query_kwargs is not None
    assert client.query_kwargs["limit"] == 10
    query_filter = client.query_kwargs["query_filter"]
    assert query_filter.must[0].key == "user_id"  # type: ignore[union-attr]
    assert query_filter.must[0].match.value == str(user_id)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_upsert_payload_has_required_ownership_fields() -> None:
    store = VectorStore()
    client = FakeVectorClient()
    store.client = client  # type: ignore[assignment]
    point = VectorPoint(
        point_id=str(uuid.uuid4()),
        vector=[0.2] * 1024,
        user_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        heading_path="退款政策 > 流程",
    )

    await store.upsert_chunks([point])

    payload = client.upserted[0].payload  # type: ignore[index,union-attr]
    assert payload == {
        "user_id": str(point.user_id),
        "document_id": str(point.document_id),
        "chunk_id": str(point.chunk_id),
        "heading_path": "退款政策 > 流程",
        "embedding_model": store.settings.embedding_model,
    }


class FakeEmbeddingSession:
    def __init__(self) -> None:
        self.rows: list[Embedding] = []
        self.added: list[Embedding] = []

    async def scalars(self, _: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.rows)

    def add_all(self, embeddings: list[Embedding]) -> None:
        self.added.extend(embeddings)

    async def flush(self) -> None:
        self.rows.extend(self.added)
        self.added.clear()

    @asynccontextmanager
    async def begin_nested(self):  # type: ignore[no-untyped-def]
        yield


class FakeLlm:
    def __init__(self) -> None:
        self.calls = 0

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.1] * 1024 for _ in texts]


@pytest.mark.asyncio
async def test_embedding_cache_avoids_duplicate_model_calls() -> None:
    session = FakeEmbeddingSession()
    llm = FakeLlm()

    first = await get_or_create_embeddings(session, llm, ["相同文本", "相同文本", "另一段文本"])
    second = await get_or_create_embeddings(session, llm, ["相同文本", "另一段文本"])

    assert len(first) == 2
    assert second == first
    assert llm.calls == 1
