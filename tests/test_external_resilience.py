from types import SimpleNamespace

import pytest

from app.services.llm import LlmClient


@pytest.mark.asyncio
async def test_llm_request_retries_transient_failures() -> None:
    client = LlmClient.__new__(LlmClient)
    client.settings = SimpleNamespace(external_max_retries=2, llm_timeout_seconds=1.0)
    attempts = 0

    async def intermittent() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary provider failure")
        return "ok"

    assert await client._request(intermittent) == "ok"
    assert attempts == 2
