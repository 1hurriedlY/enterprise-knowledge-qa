from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text

from app.bootstrap import seed_demo_identity
from app.config import get_settings
from app.database import SessionLocal, engine
from app.routers.chat import router as chat_router
from app.routers.files import router as files_router
from app.schemas import HealthResponse
from app.services.vector_store import VectorStore

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with SessionLocal() as session:
        await seed_demo_identity(session)
    yield
    await engine.dispose()


app = FastAPI(
    title="企业知识库智能客服系统",
    version="0.1.0",
    description="基于 RAG 与 Tool Calling 的初级企业知识库客服系统。",
    lifespan=lifespan,
)
app.include_router(files_router)
app.include_router(chat_router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    database_ok = vector_ok = redis_ok = False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        pass
    try:
        vector_ok = await VectorStore().health()
    except Exception:
        pass
    try:
        redis = Redis.from_url(settings.redis_url)
        await redis.ping()
        await redis.aclose()
        redis_ok = True
    except Exception:
        pass

    llm_key = settings.llm_api_key.get_secret_value()
    llm_ok = bool(llm_key and llm_key != "replace-me")
    app_status: Literal["ok", "degraded"] = (
        "ok" if all((database_ok, vector_ok, redis_ok, llm_ok)) else "degraded"
    )
    return HealthResponse(
        status=app_status,
        app="ok",
        database="ok" if database_ok else "error",
        vector_db="ok" if vector_ok else "error",
        redis="ok" if redis_ok else "error",
        llm="ok" if llm_ok else "error",
    )
