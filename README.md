# 企业知识库智能客服系统

基于 FastAPI、PostgreSQL、Redis、Qdrant 与 OpenAI 兼容接口的初级企业知识库智能客服系统。支持 PDF / Markdown / TXT 文档入库、带引用的 RAG 问答、订单与物流查询、人工工单，以及管理员审计查询。

架构与安全边界见 [架构文档](docs/architecture.md)。

## 快速启动

1. 复制 `.env.example` 为 `.env`，填写云百炼兼容接口的 `LLM_API_KEY` 和本地 `DEMO_API_KEY`。
2. 启动服务：`docker compose up --build`。
3. 打开 [Swagger UI](http://localhost:8000/docs)，或请求 [健康检查](http://localhost:8000/health)。

Docker Compose 会启动 API、异步 Worker、PostgreSQL、Redis 和 Qdrant。首次启动会创建演示管理员、API Key 对应身份以及订单 `12345` 的模拟数据。

## 身份与安全

除 `GET /health` 外，每个业务接口都需要请求头 `X-API-Key`。携带 `user_id` 的请求还会校验该 ID 是否与 API Key 所属用户一致。管理员接口还需 `admin` 角色。

不要提交 `.env`。虚拟环境、缓存、上传原文件与本地运行数据已由 `.gitignore` 排除。

## 核心接口

| 功能 | 接口 |
| --- | --- |
| 上传 / 管理文档 | `POST /api/v1/files/upload`、`GET /api/v1/files`、`DELETE /api/v1/files/{document_id}` |
| 创建会话与问答 | `POST /api/v1/conversations`、`POST /api/v1/chat` |
| 查看消息历史 | `GET /api/v1/conversations/{conversation_id}/messages` |
| 管理员请求日志 | `GET /api/v1/admin/logs?limit=50` |
| 管理员工具记录 | `GET /api/v1/admin/tool-calls?limit=50` |
| 健康检查 | `GET /health` |

管理员审计输出会对可能出现的 API Key、Bearer Token、密码等文本脱敏。

## 开发检查

Windows PowerShell：

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m compileall -q app
```

评测场景位于 [evals/cases.json](evals/cases.json)，覆盖上传、RAG、工具、安全和权限的 PRD 验收项。
