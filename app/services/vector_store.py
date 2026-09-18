import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings, get_settings


@dataclass(frozen=True)
class VectorPoint:
    point_id: str
    vector: list[float]
    user_id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    heading_path: str


class VectorStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = AsyncQdrantClient(url=str(self.settings.qdrant_url))

    async def ensure_collection(self) -> None:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            await self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_dimension, distance=models.Distance.COSINE
                ),
            )
            await self.client.create_payload_index(
                self.settings.qdrant_collection,
                field_name="user_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                self.settings.qdrant_collection,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    async def upsert_chunk(
        self,
        point_id: str,
        vector: list[float],
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        chunk_id: uuid.UUID,
        heading_path: str,
    ) -> None:
        await self.upsert_chunks(
            [
                VectorPoint(
                    point_id=point_id,
                    vector=vector,
                    user_id=user_id,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    heading_path=heading_path,
                )
            ]
        )

    async def upsert_chunks(self, points: Sequence[VectorPoint]) -> None:
        if not points:
            return
        await self.ensure_collection()
        await self.client.upsert(
            collection_name=self.settings.qdrant_collection,
            points=[
                models.PointStruct(
                    id=point.point_id,
                    vector=point.vector,
                    payload={
                        "user_id": str(point.user_id),
                        "document_id": str(point.document_id),
                        "chunk_id": str(point.chunk_id),
                        "heading_path": point.heading_path,
                        "embedding_model": self.settings.embedding_model,
                    },
                )
                for point in points
            ],
            wait=True,
        )

    async def search(
        self, user_id: uuid.UUID, vector: list[float], limit: int = 10
    ) -> list[tuple[uuid.UUID, float]]:
        await self.ensure_collection()
        limit = min(max(limit, 1), 10)
        result = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=str(user_id))
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )
        return [
            (uuid.UUID(str(point.payload["chunk_id"])), float(point.score))
            for point in result.points
            if point.payload and point.payload.get("chunk_id")
        ]

    async def delete_points(self, point_ids: Sequence[int | str | uuid.UUID]) -> None:
        if point_ids:
            await self.client.delete(
                collection_name=self.settings.qdrant_collection,
                points_selector=models.PointIdsList(points=list(point_ids)),
                wait=True,
            )

    async def health(self) -> bool:
        try:
            await self.client.get_collections()
        except Exception:
            return False
        return True
