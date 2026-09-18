import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.bootstrap import seed_demo_identity
from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import RequestLog
from app.routers.admin import router as admin_router
from app.routers.chat import router as chat_router
from app.routers.files import router as files_router
from app.routers.users import router as users_router
from app.schemas import HealthResponse
from app.services.redaction import redact_text
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
    summary="支持文档入库、RAG 问答与订单工具的企业知识库客服 API。",
    description=(
        "基于 FastAPI、PostgreSQL、Redis、Qdrant 和 OpenAI 兼容接口的初级企业知识库客服系统。"
        "除健康检查外，所有业务接口均需要 X-API-Key。"
    ),
    openapi_tags=[
        {"name": "users", "description": "当前 API Key 所属用户的身份信息。"},
        {"name": "files", "description": "用户自己的文档上传、查询和删除。"},
        {"name": "chat", "description": "用户自己的会话、消息历史和知识库问答。"},
        {"name": "admin", "description": "仅管理员可访问的脱敏审计记录。"},
        {"name": "system", "description": "服务依赖健康状态。"},
    ],
    lifespan=lifespan,
)
app.include_router(files_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(users_router)


@app.middleware("http")
async def audit_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Persist a minimal audit trail for every non-chat request.

    Chat requests write a richer record in the service layer and mark
    ``audit_logged`` to prevent a duplicate entry.
    """
    request.state.request_id = str(uuid.uuid4())
    started = time.perf_counter()
    response: Response | None = None
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
    finally:
        if not getattr(request.state, "audit_logged", False):
            try:
                async with SessionLocal() as session:
                    session.add(
                        RequestLog(
                            request_id=request.state.request_id,
                            user_id=getattr(request.state, "user_id", None),
                            path=request.url.path,
                            method=request.method,
                            query=redact_text(str(request.query_params)) or None,
                            retrieved_chunks=[],
                            tool_calls=[],
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            status_code=response.status_code if response is not None else 500,
                            error_message=None if response is not None else "请求处理失败",
                        )
                    )
                    await session.commit()
            except Exception:
                # Audit failure must never hide the original business response.
                pass


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
