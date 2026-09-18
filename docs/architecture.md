# 系统架构

```mermaid
flowchart TD
    U[用户 / 管理员] --> API[FastAPI API]
    API --> AUTH[API Key 鉴权与角色校验]

    AUTH --> UPLOAD[上传文档]
    UPLOAD --> FS[本地文件存储]
    UPLOAD --> DOC[(PostgreSQL documents)]
    UPLOAD --> Q[Redis 队列]
    Q --> W[ARQ 入库 Worker]
    W --> PARSE[解析、清洗、标题优先切片]
    PARSE --> EMB[OpenAI 兼容 Embedding]
    EMB --> VDB[(Qdrant 向量库)]
    PARSE --> CHUNK[(PostgreSQL chunks / embeddings)]

    AUTH --> CHAT[知识库问答]
    CHAT --> HISTORY[最近 5 轮历史]
    HISTORY --> REWRITE[Query Rewrite]
    REWRITE --> INTENT[意图识别]
    INTENT -->|知识库问答| RETRIEVE[Qdrant 检索：user_id 过滤]
    RETRIEVE --> RAG[严格 RAG Prompt]
    INTENT -->|订单 / 物流 / 人工| TOOL[参数校验与工具调用]
    TOOL --> BIZ[(模拟订单、物流、工单)]
    TOOL --> SUMMARY[工具结果总结]
    INTENT -->|敏感 / 无关 / 注入| REFUSE[安全拒答]
    RAG --> SAVE[保存消息、引用与审计日志]
    SUMMARY --> SAVE
    REFUSE --> SAVE
    SAVE --> RESP[答案、来源、工具记录]

    AUTH --> ADMIN[管理员审计查询]
    ADMIN --> LOGS[(request_logs / tool_calls)]
```

## 安全边界

- 所有业务 API 需要 `X-API-Key`；请求中的 `user_id` 必须与密钥所属用户一致。
- 文档、会话、订单和向量检索均按用户归属隔离；Qdrant 检索始终附带 `user_id` 过滤。
- 管理员日志和工具记录接口额外校验 `admin` 角色，并对可能的密钥文本脱敏。
- `.env`、上传原文件、虚拟环境和缓存均不进入 Git。
