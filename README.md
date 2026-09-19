# 企业知识库智能客服系统

基于 FastAPI、PostgreSQL、Redis、Qdrant 与 OpenAI 兼容接口的初级企业知识库智能客服系统。支持 PDF / Markdown / TXT 文档入库、带引用的 RAG 问答、订单与物流查询、人工工单，以及管理员审计查询。

架构与安全边界见 [架构文档](docs/architecture.md)。

## 功能与技术栈

- 文档：异步上传、Markdown / TXT / PDF 解析、清洗、标题优先切片与向量删除同步。
- 问答：历史改写、意图识别、Qdrant 用户隔离检索、严格引用、安全拒答与 SSE 分段交付。
- 工具：模拟订单、物流、转人工工单，以及工具超时与失败处理。
- 审计：请求、引用和工具调用记录；管理员只读查询与敏感信息脱敏。

技术栈：Vue 3、TypeScript、Element Plus、Nginx、Python 3.12、FastAPI、SQLAlchemy Async、Alembic、PostgreSQL、Redis + ARQ、Qdrant、Docker Compose、OpenAI 兼容 LLM / Embedding 接口。

## 快速启动

1. 复制 `.env.example` 为 `.env`，填写云百炼兼容接口的 `LLM_API_KEY` 和本地 `DEMO_API_KEY`。
2. 启动服务：`docker compose up --build`。
3. 打开 [前端界面](http://localhost:8080)，在“设置与 API Key”中保存本地 `DEMO_API_KEY`。
4. 可选：打开 [Swagger UI](http://localhost:8000/docs)，或请求 [健康检查](http://localhost:8000/health)。

Docker Compose 会启动前端、API、异步 Worker、PostgreSQL、Redis 和 Qdrant。首次启动会创建演示管理员、API Key 对应身份以及订单 `12345` 的模拟数据。

前端由 Nginx 提供静态页面，并将 `/api` 和 `/health` 代理到 Compose 内的 API 服务；浏览器不会读取根目录 `.env` 或模型服务密钥。

## 前端使用

访问 [http://localhost:8080](http://localhost:8080)，然后：

1. 在“设置与 API Key”中粘贴 `.env` 中的 `DEMO_API_KEY`，点击“保存到本会话”和“验证 API Key”。该值仅保存在当前浏览器标签页中，关闭标签页后自动清除。
2. 在“知识文档”上传 PDF、Markdown 或 TXT 文件。处理状态完成后，可在“智能对话”中提问并查看引用来源。
3. 演示 API Key 默认属于管理员，因此也可在“管理后台”查看服务端脱敏后的审计记录。

仅开发前端时，可运行：

```powershell
cd frontend
npm install
npm run dev
```

开发地址为 `http://localhost:5173`，同样会将 API 请求代理到 `http://localhost:8000`。

## 环境变量

| 变量                                        | 说明                             |
| ------------------------------------------- | -------------------------------- |
| `LLM_BASE_URL` / `LLM_API_KEY`              | OpenAI 兼容的模型服务地址和密钥  |
| `CHAT_MODEL` / `EMBEDDING_MODEL`            | 聊天与向量模型名称               |
| `EMBEDDING_DIMENSION`                       | Embedding 向量维度，须和模型匹配 |
| `DEMO_API_KEY`                              | 本地演示身份的长随机 API Key     |
| `DATABASE_URL` / `REDIS_URL` / `QDRANT_URL` | Compose 内部依赖连接地址         |
| `MAX_UPLOAD_BYTES`                          | 单个文件上限，默认 10 MB         |
| `RETRIEVAL_SCORE_THRESHOLD`                 | 检索最低相似度分数，默认 0.30    |

完整模板见 `.env.example`；不要将 `.env` 或任何真实密钥提交到 Git。

## 身份与安全

除 `GET /health` 外，每个业务接口都需要请求头 `X-API-Key`。携带 `user_id` 的请求还会校验该 ID 是否与 API Key 所属用户一致。管理员接口还需 `admin` 角色。

不要提交 `.env`。虚拟环境、缓存、上传原文件与本地运行数据已由 `.gitignore` 排除。

## 核心接口

| 功能                 | 接口                                                                                            |
| -------------------- | ----------------------------------------------------------------------------------------------- |
| 上传 / 管理文档      | `POST /api/v1/files/upload`、`GET /api/v1/files`、`DELETE /api/v1/files/{document_id}`          |
| 创建会话与问答       | `POST /api/v1/conversations`、`POST /api/v1/chat`、`POST /api/v1/chat/stream`                   |
| 查看消息历史         | `GET /api/v1/conversations/{conversation_id}/messages`                                          |
| 管理员会话与消息记录 | `GET /api/v1/admin/conversations`、`GET /api/v1/admin/conversations/{conversation_id}/messages` |
| 管理员请求日志       | `GET /api/v1/admin/logs?limit=50`                                                               |
| 管理员工具记录       | `GET /api/v1/admin/tool-calls?limit=50`                                                         |
| 健康检查             | `GET /health`                                                                                   |

管理员审计输出会对可能出现的 API Key、Bearer Token、密码等文本脱敏。

## 示例请求与响应

创建会话后，以同一用户的 API Key 发送订单问题：

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"user_id":"<your-user-uuid>","conversation_id":"<conversation-uuid>","query":"我的订单 12345 发货了吗？"}'
```

成功响应会包含意图和工具审计摘要：

```json
{
  "answer": "您的订单 12345 已发货。",
  "intent": "order_query",
  "need_human": false,
  "tool_calls": [{ "tool_name": "query_order", "status": "success" }]
}
```

`POST /api/v1/chat/stream` 使用相同请求体和鉴权头，返回 `text/event-stream`。浏览器前端会消费 `delta`、`complete` 和安全的 `error` 事件并逐段渲染答案；服务端只在现有 RAG、引用和结构化校验完成后再开始发送内容。

## 开发检查

Windows PowerShell：

```powershell
.\.venv\Scripts\ruff.exe check app tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m compileall -q app
```

评测场景位于 [evals/cases.json](evals/cases.json)，覆盖上传、RAG、工具、安全和权限的 PRD 验收项。
已发现问题与修复措施见 [Bad Case 分析](docs/bad-case-analysis.md)。

## 评测结果

当前回归套件有 38 项自动测试，覆盖上传和解析、嵌入缓存、用户隔离检索、RAG 引用与安全拒答、工具调用和超时、管理员权限、审计脱敏及评测集格式。最终容器验收同时检查健康状态、迁移一致性和 OpenAPI 路由。

## 已知问题

- 初级版使用本地卷保存上传原文件、PostgreSQL 模拟订单与物流数据；生产环境应迁移到对象存储和真实业务系统。
- 评测集当前是版本化验收场景清单；完整的模型质量指标（正确性、来源正确性、幻觉率、完整性）需在稳定业务语料上持续统计。
- LLM 依赖外部兼容接口，网络与供应商限流会影响端到端响应时间。

## 后续规划

- 接入对象存储、真实订单/物流/工单服务与密钥管理。
- 将评测集接入自动化执行与质量趋势报告，使用 Bad Case 调整检索阈值和 Prompt。
- 增加管理员分页筛选、观测指标与生产级限流、告警和备份策略。
