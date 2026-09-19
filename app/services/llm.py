import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.prompts import SYSTEM_PROMPT_V1

ModelT = TypeVar("ModelT", bound=BaseModel)


class LlmOutputError(ValueError):
    pass


class LlmClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.client = AsyncOpenAI(
            base_url=str(self.settings.llm_base_url),
            api_key=self.settings.llm_api_key.get_secret_value(),
        )

    def _track_usage(self, response: object) -> None:
        """Accumulate optional usage fields returned by compatible providers."""
        usage = getattr(response, "usage", None)
        self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

    async def _request(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        """Run one provider call with bounded retries and a hard deadline."""
        retries = self.settings.external_max_retries
        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(
                    operation(), timeout=self.settings.llm_timeout_seconds
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt == retries:
                    raise LlmOutputError("模型服务暂时不可用") from exc
                await asyncio.sleep(0.1 * (attempt + 1))
        raise AssertionError("unreachable")

    async def structured(self, prompt: str, result_type: type[ModelT]) -> ModelT:
        response = await self._request(
            lambda: self.client.chat.completions.create(
                model=self.settings.chat_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_V1},
                    {"role": "user", "content": prompt},
                ],
            )
        )
        self._track_usage(response)
        content = response.choices[0].message.content
        if not content:
            raise LlmOutputError("模型未返回内容")
        try:
            return result_type.model_validate_json(content)
        except ValidationError as exc:
            raise LlmOutputError("模型返回格式无效") from exc

    async def text(self, prompt: str) -> str:
        response = await self._request(
            lambda: self.client.chat.completions.create(
                model=self.settings.chat_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_V1},
                    {"role": "user", "content": prompt},
                ],
            )
        )
        self._track_usage(response)
        content = response.choices[0].message.content
        if not content:
            raise LlmOutputError("模型未返回内容")
        return str(content).strip()

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_many([text]))[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Create embeddings in one compatible-API request, preserving input order."""
        if not texts:
            return []
        response = await self._request(
            lambda: self.client.embeddings.create(
                model=self.settings.embedding_model, input=texts
            )
        )
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts):
            raise LlmOutputError("Embedding 返回数量与输入不一致")
        return vectors

    async def health(self) -> bool:
        """Verify that the configured chat model is reachable without exposing secrets."""
        try:
            await self._request(
                lambda: self.client.chat.completions.create(
                    model=self.settings.chat_model,
                    messages=[{"role": "user", "content": "health check"}],
                    max_tokens=1,
                )
            )
        except LlmOutputError:
            return False
        return True


def render_history(history: list[tuple[str, str]]) -> str:
    return "\n".join(f"{role}：{content}" for role, content in history) or "（无历史对话）"


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
