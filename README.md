# 企业知识库智能客服系统

基于 FastAPI、RAG、Qdrant 和 Tool Calling 的初级企业知识库客服项目。

## 当前进度

已完成第 1 步：项目骨架、容器编排、环境配置、数据库迁移基础、API Key 身份模型与健康检查。

## 本地启动

1. 复制 `.env.example` 为 `.env`。默认配置使用云百炼 OpenAI 兼容地址、`qwen-plus` 和 `text-embedding-v4`；为 `DEMO_API_KEY` 和 `LLM_API_KEY` 设置真实值。
2. 执行 `docker compose up --build`。
3. 打开 `http://localhost:8000/docs` 或访问 `http://localhost:8000/health`。

不要将 `.env` 提交到版本库。
