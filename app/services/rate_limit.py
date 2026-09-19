"""Redis-backed fixed-window request limiting."""

import hashlib
import logging
import time
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


def request_identities(request: Request) -> tuple[str, ...]:
    host = request.client.host if request.client is not None else "unknown"
    identities = [f"ip:{host}"]
    api_key = request.headers.get("X-API-Key")
    if api_key:
        identities.append(f"api-key:{hashlib.sha256(api_key.encode('utf-8')).hexdigest()}")
    return tuple(identities)


async def consume(
    redis: Redis,
    identity: str,
    max_requests: int,
    window_seconds: int,
    now: float | None = None,
) -> RateLimitResult:
    timestamp = time.time() if now is None else now
    window = int(timestamp // window_seconds)
    key = f"rate-limit:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}:{window}"
    count = int(await redis.incr(key))
    if count == 1:
        await redis.expire(key, window_seconds + 1)
    remaining = max(0, window_seconds - int(timestamp % window_seconds))
    return RateLimitResult(allowed=count <= max_requests, retry_after=remaining)


async def check_request_limit(request: Request, settings: Settings) -> RateLimitResult | None:
    if not settings.rate_limit_enabled or request.url.path in {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }:
        return None
    redis: Redis | None = None
    try:
        redis = Redis.from_url(settings.redis_url)
        results = [
            await consume(
                redis,
                identity,
                settings.rate_limit_requests,
                settings.rate_limit_window_seconds,
            )
            for identity in request_identities(request)
        ]
        blocked = [result for result in results if not result.allowed]
        if blocked:
            return RateLimitResult(False, max(result.retry_after for result in blocked))
        return RateLimitResult(True, min(result.retry_after for result in results))
    except Exception:
        if settings.rate_limit_fail_open:
            logger.warning("rate limiter unavailable; allowing request", exc_info=True)
            return None
        logger.error("rate limiter unavailable; rejecting request", exc_info=True)
        return RateLimitResult(False, settings.rate_limit_window_seconds)
    finally:
        if redis is not None:
            await redis.aclose()
