import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.domain import UserRole
from app.models import ApiKey, User
from app.routers.auth import generate_api_key, register
from app.schemas import RegisterRequest
from app.services import rate_limit
from app.services.auth import hash_api_key
from app.services.passwords import hash_password, verify_password
from app.services.rate_limit import consume, request_identities


def test_password_hash_round_trip_and_random_salt() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("correct horse battery staple", "malformed")


def test_api_key_is_random_and_only_hash_is_persisted() -> None:
    raw_key = generate_api_key()

    assert raw_key.startswith("kb_")
    assert len(raw_key) >= 40
    assert hash_api_key(raw_key) != raw_key


def test_registration_schema_rejects_short_password_and_bad_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(name="User", email="not-an-email", password="short")


class FakeAuthSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    async def scalar(self, _: object) -> None:
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if isinstance(value, User) and value.id is None:
                value.id = uuid.uuid4()
                value.role = UserRole.USER
                value.created_at = datetime.now(UTC)
                value.updated_at = value.created_at
            if isinstance(value, ApiKey) and value.id is None:
                value.id = uuid.uuid4()
                value.created_at = datetime.now(UTC)

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_register_returns_raw_key_but_stores_only_hash() -> None:
    session = FakeAuthSession()
    response = await register(
        RegisterRequest(name="New User", email="New@Example.com", password="password-123"),
        session,  # type: ignore[arg-type]
    )

    key = next(value for value in session.added if isinstance(value, ApiKey))
    assert response.email == "new@example.com"
    assert response.api_key.startswith("kb_")
    assert key.key_hash == hash_api_key(response.api_key)
    assert key.key_hash != response.api_key
    assert session.committed


@pytest.mark.asyncio
async def test_fixed_window_rate_limit_blocks_after_limit() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}
            self.expirations: dict[str, int] = {}

        async def incr(self, key: str) -> int:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, key: str, seconds: int) -> bool:
            self.expirations[key] = seconds
            return True

    redis = FakeRedis()
    first = await consume(redis, "api-key:test", max_requests=2, window_seconds=60, now=120)
    second = await consume(redis, "api-key:test", max_requests=2, window_seconds=60, now=121)
    third = await consume(redis, "api-key:test", max_requests=2, window_seconds=60, now=122)

    assert first.allowed and second.allowed
    assert not third.allowed
    assert third.retry_after == 58
    assert len(redis.expirations) == 1


def test_rate_limit_identity_always_includes_client_ip() -> None:
    from starlette.requests import Request

    def make_request(raw_key: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/login",
                "headers": [(b"x-api-key", raw_key.encode())],
                "client": ("127.0.0.1", 1234),
                "scheme": "http",
            }
        )

    first = request_identities(make_request("kb-first"))
    second = request_identities(make_request("kb-second"))

    assert first[0] == second[0] == "ip:127.0.0.1"
    assert first[1] != second[1]


@pytest.mark.asyncio
async def test_rate_limit_can_fail_open_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users/me",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
        }
    )

    def fail_from_url(_: str) -> object:
        raise RuntimeError("redis down")

    monkeypatch.setattr(rate_limit.Redis, "from_url", fail_from_url)
    settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_fail_open=True,
        redis_url="redis://unavailable",
        rate_limit_requests=60,
        rate_limit_window_seconds=60,
    )

    assert await rate_limit.check_request_limit(request, settings) is None  # type: ignore[arg-type]
