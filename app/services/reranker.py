"""Optional Cohere-compatible reranking adapter for retrieved chunks."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings


class RerankError(RuntimeError):
    """Raised when an enabled rerank provider returns an unusable response."""


@dataclass(frozen=True)
class RerankScore:
    index: int
    score: float


def parse_rerank_scores(payload: object, document_count: int) -> list[RerankScore]:
    """Validate provider output and reject duplicate or out-of-range indices."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise RerankError("rerank response has no results")
    scores: list[RerankScore] = []
    seen: set[int] = set()
    for item in payload["results"]:
        if not isinstance(item, dict):
            raise RerankError("rerank result is not an object")
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index >= document_count
            or index in seen
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0 <= float(score) <= 1
        ):
            raise RerankError("rerank result contains invalid index or score")
        seen.add(index)
        scores.append(RerankScore(index=index, score=float(score)))
    return scores


class RerankClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def _request(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        retries = self.settings.external_max_retries
        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(
                    operation(), timeout=self.settings.rerank_timeout_seconds
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt == retries:
                    raise RerankError("rerank provider unavailable") from exc
                await asyncio.sleep(0.1 * (attempt + 1))
        raise AssertionError("unreachable")

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int | None = None
    ) -> list[RerankScore]:
        if not self.settings.rerank_enabled or not documents:
            return []
        if not self.settings.rerank_model:
            raise RerankError("rerank model is not configured")
        base_url = str(self.settings.rerank_base_url or self.settings.llm_base_url).rstrip("/")
        api_key = (self.settings.rerank_api_key or self.settings.llm_api_key).get_secret_value()
        request_top_n = top_n or self.settings.rerank_top_n

        async def call() -> object:
            async with httpx.AsyncClient(
                timeout=self.settings.rerank_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{base_url}/rerank",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self.settings.rerank_model,
                        "query": query,
                        "documents": list(documents),
                        "top_n": min(max(request_top_n, 1), len(documents)),
                        "return_documents": False,
                    },
                )
                response.raise_for_status()
                return response.json()

        payload = await self._request(call)
        return parse_rerank_scores(payload, len(documents))
