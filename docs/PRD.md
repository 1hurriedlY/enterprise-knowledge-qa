> **企业知识库智能客服系统（初级版）**

你可以把这份内容直接复制到你的项目文档里，例如：

```text
docs/PRD.md
docs/PROMPTS.md
README.md
```

---

# 第一部分：初级项目需求文档

---

# 1. 项目概述

## 1.1 项目名称

```text
企业知识库智能客服系统（初级版）
```

## 1.2 项目目标

构建一个基于大模型、RAG 和 Tool Calling 的智能客服系统。

系统允许用户上传企业知识文档，例如：

```text
PDF
Markdown
TXT
```

系统会自动完成：

```text
文档解析
文本清洗
文档切片
Embedding 向量化
向量库存储
```

用户提问后，系统能够：

```text
检索知识库相关内容
结合大模型生成回答
返回引用来源
必要时调用业务工具
无法解决时引导转人工
```

---

## 1.3 项目定位

这是一个 **初级可展示项目**，目标是证明你具备以下能力：

```text
1. Python 工程化开发能力
2. FastAPI 接口开发能力
3. LLM API 调用能力
4. Prompt 设计能力
5. RAG 知识库问答能力
6. 向量数据库使用能力
7. Tool Calling 工具调用能力
8. 日志记录能力
9. Docker 部署能力
10. 简单评测和优化能力
```

---

## 1.4 项目不做什么

初级版不要做太复杂，以下内容暂时不作为核心需求：

```text
不做复杂多 Agent
不做 LangGraph 工作流
不做多租户复杂权限
不做知识图谱
不做模型微调
不做大规模分布式部署
不做复杂前端
不做自动化训练平台
```

这些属于中级升级内容。

---

# 2. 用户角色

## 2.1 普通用户

普通用户可以：

```text
上传文档
创建会话
提问
查看回答
查看引用来源
查询订单
查询物流
申请转人工
```

## 2.2 管理员

管理员可以：

```text
查看会话记录
查看消息记录
查看工具调用记录
查看日志
查看系统健康状态
```

初级阶段管理员功能可以从简，不一定需要完整后台页面。

---

# 3. 核心业务场景

---

## 场景一：知识库问答

用户问：

```text
如何申请退款？
```

系统回答：

```text
您可以在订单详情页点击“申请退款”，选择退款原因后提交申请。审核通过后，退款将在 3-5 个工作日内原路返回。

来源：
1. 退款政策.md#退款流程
```

---

## 场景二：订单查询

用户问：

```text
我的订单 12345 发货了吗？
```

系统调用：

```text
query_order
```

然后回答：

```text
您的订单 12345 已发货。
```

---

## 场景三：物流查询

用户问：

```text
我的订单 12345 到哪了？
```

系统调用：

```text
query_logistics
```

然后回答：

```text
您的订单 12345 已到达北京转运中心，目前正在派送中。
```

---

## 场景四：转人工

用户问：

```text
我要投诉，给我转人工客服。
```

系统调用：

```text
transfer_to_human
```

然后回答：

```text
已为您创建人工客服工单，客服人员会尽快与您联系。
```

---

## 场景五：知识库未命中

用户问：

```text
你们公司明年股价会涨吗？
```

系统应回答：

```text
抱歉，知识库中未找到相关信息，且我无法提供投资建议。
```

---

# 4. 初级版功能范围

---

## 4.1 文档上传

系统需要支持用户上传文档。

支持格式：

```text
.md
.txt
.pdf
```

文件大小限制：

```text
单文件不超过 10 MB
```

上传后需要记录：

```text
文件名
文件类型
文件大小
上传用户
上传时间
处理状态
```

处理状态包括：

```text
pending
processing
completed
failed
```

---

## 4.2 文档解析

系统需要解析上传的文档，提取文本内容。

对于 Markdown：

```text
保留标题
保留段落
保留列表
保留代码块标记
```

对于 PDF：

```text
尽量提取正文文本
识别标题和段落
忽略明显页眉页脚
```

初级阶段允许 PDF 解析效果有限，但需要记录解析失败原因。

---

## 4.3 文本清洗

文档解析后需要清洗。

需要处理：

```text
多余空行
多余空格
乱码字符
明显页眉页脚
过短无意义片段
```

需要保留：

```text
标题层级
段落结构
列表
代码块标记
```

---

## 4.4 文档切片

系统需要将清洗后的文本切成多个 chunk。

初级默认策略：

```text
优先按标题和段落切片
如果单个片段过长，再按长度切分
每个切片保留标题路径
```

默认参数：

```text
chunk_size = 500 字左右
chunk_overlap = 50 字左右
```

每个切片需要保存：

```text
document_id
chunk_id
content
heading_path
created_at
```

示例：

```json
{
  "document_id": "doc_001",
  "chunk_id": "chunk_001",
  "content": "用户可以在订单详情页点击申请退款...",
  "heading_path": "退款政策 > 退款流程"
}
```

---

## 4.5 Embedding 向量化

每个切片需要生成向量。

要求：

```text
相同文本不重复向量化
批量处理切片
记录 Embedding 模型名称
记录向量维度
```

每个向量需要绑定 metadata：

```json
{
  "document_id": "doc_001",
  "chunk_id": "chunk_001",
  "user_id": "user_001",
  "heading_path": "退款政策 > 退款流程"
}
```

---

## 4.6 向量库存储

初级推荐：

```text
Qdrant
```

或：

```text
PGVector
```

要求支持：

```text
插入向量
删除向量
相似度检索
按用户过滤
按文档过滤
返回相似度分数
```

---

## 4.7 知识库问答

用户提问后，系统需要完成：

```text
获取历史对话
查询改写
向量检索
构造 Prompt
调用 LLM
生成回答
保存消息
返回引用来源
```

---

## 4.8 引用来源

每次回答都需要返回引用来源。

来源字段至少包括：

```text
document_id
filename
chunk_id
heading_path
chunk_content
score
```

示例：

```json
{
  "sources": [
    {
      "document_id": "doc_001",
      "filename": "退款政策.md",
      "chunk_id": "chunk_003",
      "heading_path": "退款政策 > 退款流程",
      "content": "用户可以在订单详情页点击申请退款...",
      "score": 0.86
    }
  ]
}
```

---

## 4.9 多轮对话

系统需要支持多轮对话。

要求：

```text
支持创建会话
支持保存历史消息
支持根据会话上下文理解问题
限制传入模型的历史消息数量
```

默认策略：

```text
最多保留最近 5 轮对话
如果上下文不足，则只处理当前问题
```

---

## 4.10 查询改写

当用户问题存在指代不清时，系统需要进行查询改写。

例如：

历史对话：

```text
用户：我的订单 12345 到哪了？
助手：您的订单已发货。
```

当前问题：

```text
那它什么时候到？
```

改写后：

```text
订单 12345 预计什么时候送达？
```

---

## 4.11 无答案处理

如果检索结果为空，或相似度分数过低，系统不能编造。

应返回：

```text
抱歉，知识库中未找到相关信息。
```

可选项：

```text
引导用户转人工
```

---

## 4.12 工具调用

初级版需要支持三个工具：

```text
query_order
query_logistics
transfer_to_human
```

工具调用流程：

```text
用户提问
→ 判断是否需要工具
→ 选择工具
→ 提取参数
→ 后端校验参数
→ 执行工具
→ 工具返回结果
→ 模型组织自然语言回答
```

---

## 4.13 查询订单工具

工具名：

```text
query_order
```

输入：

```json
{
  "order_id": "12345"
}
```

输出：

```json
{
  "order_id": "12345",
  "status": "已发货",
  "amount": 99.0,
  "created_at": "2026-09-01"
}
```

如果订单不存在：

```json
{
  "error_code": "ORDER_NOT_FOUND",
  "error_message": "订单不存在"
}
```

---

## 4.14 查询物流工具

工具名：

```text
query_logistics
```

输入：

```json
{
  "order_id": "12345"
}
```

输出：

```json
{
  "order_id": "12345",
  "logistics": [
    "已发货",
    "到达北京转运中心",
    "派送中"
  ]
}
```

如果物流不存在：

```json
{
  "error_code": "LOGISTICS_NOT_FOUND",
  "error_message": "物流信息不存在"
}
```

---

## 4.15 转人工工具

工具名：

```text
transfer_to_human
```

输入：

```json
{
  "reason": "用户要求人工客服",
  "conversation_id": "conv_001"
}
```

输出：

```json
{
  "ticket_id": "ticket_001",
  "status": "created"
}
```

---

## 4.16 工具调用异常处理

工具调用失败时，系统不能直接暴露内部错误。

需要处理：

```text
参数缺失
参数格式错误
工具超时
工具返回空
订单不存在
物流不存在
转人工失败
模型调用不存在的工具
```

返回给用户的文案要友好：

```text
抱歉，暂时无法查询到您的订单信息，请稍后重试或联系人工客服。
```

---

## 4.17 日志记录

每次请求需要记录：

```text
request_id
user_id
conversation_id
query
rewrite_query
intent
retrieved_chunks
tool_calls
llm_prompt_tokens
llm_completion_tokens
latency_ms
status_code
error_message
created_at
```

工具调用需要记录：

```text
tool_name
tool_input
tool_output
status
error_message
latency_ms
```

---

## 4.18 权限控制

初级版权限可以简单做。

要求：

```text
用户只能访问自己上传的文档
用户只能访问自己的会话
向量检索时必须带 user_id 或 document 权限过滤
```

如果未做登录系统，可以先用：

```text
user_id
API Key
```

模拟用户身份。

---

## 4.19 健康检查

系统需要提供：

```text
GET /health
```

返回：

```json
{
  "status": "ok",
  "app": "ok",
  "database": "ok",
  "vector_db": "ok",
  "llm": "ok"
}
```

---

# 5. 接口需求

---

## 5.1 上传文档

```text
POST /api/v1/files/upload
```

请求：

```text
file: 文件
user_id: 用户 ID
```

返回：

```json
{
  "document_id": "doc_001",
  "filename": "退款政策.md",
  "status": "processing"
}
```

---

## 5.2 查询文档列表

```text
GET /api/v1/files
```

返回：

```json
{
  "documents": [
    {
      "document_id": "doc_001",
      "filename": "退款政策.md",
      "status": "completed",
      "chunk_count": 28,
      "created_at": "2026-09-18T10:00:00"
    }
  ]
}
```

---

## 5.3 删除文档

```text
DELETE /api/v1/files/{document_id}
```

返回：

```json
{
  "document_id": "doc_001",
  "status": "deleted"
}
```

删除时需要同时删除：

```text
数据库记录
向量库向量
本地文件，如果保存了本地文件
```

---

## 5.4 创建会话

```text
POST /api/v1/conversations
```

请求：

```json
{
  "user_id": "user_001",
  "title": "退款咨询"
}
```

返回：

```json
{
  "conversation_id": "conv_001",
  "title": "退款咨询",
  "created_at": "2026-09-18T10:00:00"
}
```

---

## 5.5 知识库问答

```text
POST /api/v1/chat
```

请求：

```json
{
  "user_id": "user_001",
  "conversation_id": "conv_001",
  "query": "如何申请退款？"
}
```

返回：

```json
{
  "conversation_id": "conv_001",
  "answer": "您可以在订单详情页点击申请退款...",
  "sources": [
    {
      "document_id": "doc_001",
      "filename": "退款政策.md",
      "chunk_id": "chunk_003",
      "heading_path": "退款政策 > 退款流程",
      "content": "用户可以在订单详情页点击申请退款...",
      "score": 0.86
    }
  ],
  "need_human": false,
  "tool_calls": []
}
```

---

## 5.6 查询会话历史

```text
GET /api/v1/conversations/{conversation_id}/messages
```

返回：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "如何申请退款？",
      "created_at": "2026-09-18T10:00:00"
    },
    {
      "role": "assistant",
      "content": "您可以在订单详情页点击申请退款...",
      "sources": [],
      "created_at": "2026-09-18T10:00:05"
    }
  ]
}
```

---

## 5.7 后台日志

```text
GET /api/v1/admin/logs
```

返回：

```json
{
  "logs": [
    {
      "request_id": "req_001",
      "user_id": "user_001",
      "query": "如何申请退款？",
      "intent": "knowledge_qa",
      "latency_ms": 1320,
      "status_code": 200,
      "created_at": "2026-09-18T10:00:00"
    }
  ]
}
```

---

## 5.8 工具调用记录

```text
GET /api/v1/admin/tool-calls
```

返回：

```json
{
  "tool_calls": [
    {
      "tool_call_id": "tool_001",
      "conversation_id": "conv_001",
      "tool_name": "query_logistics",
      "tool_input": {
        "order_id": "12345"
      },
      "tool_output": {
        "order_id": "12345",
        "logistics": [
          "已发货",
          "到达北京转运中心",
          "派送中"
        ]
      },
      "status": "success",
      "latency_ms": 320
    }
  ]
}
```

---

# 6. 数据模型需求

---

## 6.1 users

```text
id
name
email
password_hash
role
created_at
updated_at
```

---

## 6.2 documents

```text
id
user_id
filename
file_type
file_path
status
chunk_count
created_at
updated_at
```

status：

```text
pending
processing
completed
failed
deleted
```

---

## 6.3 chunks

```text
id
document_id
content
heading_path
chunk_index
embedding_id
metadata
created_at
```

---

## 6.4 conversations

```text
id
user_id
title
created_at
updated_at
```

---

## 6.5 messages

```text
id
conversation_id
role
content
sources
created_at
```

role：

```text
user
assistant
tool
system
```

---

## 6.6 tool_calls

```text
id
conversation_id
message_id
tool_name
tool_input
tool_output
status
error_message
latency_ms
created_at
```

status：

```text
pending
success
failed
timeout
```

---

## 6.7 logs

```text
id
request_id
user_id
conversation_id
path
method
query
intent
latency_ms
status_code
error_message
created_at
```

---

# 7. RAG 处理规则

---

## 7.1 文档入库流程

```text
用户上传文件
→ 保存文件
→ 创建 documents 记录，状态 pending
→ 解析文档
→ 清洗文本
→ 切片
→ 生成 Embedding
→ 写入向量库
→ 写入 chunks 表
→ 更新 documents 状态为 completed
```

如果失败：

```text
更新 documents 状态为 failed
记录 error_message
```

---

## 7.2 用户问答流程

```text
用户提问
→ 获取会话历史
→ Query Rewrite
→ 判断意图
→ 如果知识库问答，则检索
→ 如果工具调用，则调用工具
→ 构造 Prompt
→ 调 LLM
→ 保存消息
→ 返回回答和来源
```

---

## 7.3 检索规则

默认：

```text
top_k = 10
```

进入 Prompt 的片段：

```text
最多 3～5 条
```

相似度分数低于阈值时：

```text
不进入 Prompt
```

默认阈值可以设置：

```text
0.25 到 0.35 之间，根据实际模型调整
```

---

## 7.4 引用来源规则

每个进入 Prompt 的片段都要有编号：

```text
[1]
[2]
[3]
```

回答中如果引用某段内容，需要标注来源编号。

---

# 8. 非功能需求

---

## 8.1 性能要求

初级目标：

```text
普通知识库问答响应时间尽量控制在 5 秒内
工具调用响应时间尽量控制在 3 秒内
文档解析允许异步或稍慢
```

---

## 8.2 稳定性要求

系统需要支持：

```text
LLM 超时
LLM 重试
Embedding 超时
工具调用超时
向量库连接失败处理
数据库连接失败处理
```

---

## 8.3 安全要求

系统需要做到：

```text
不允许模型泄露系统提示词
不允许用户访问别人的文档
日志中不记录敏感密钥
上传文件限制类型和大小
接口参数必须校验
```

---

## 8.4 可维护性要求

代码需要：

```text
结构清晰
配置分离
日志完整
类型注解
异常处理
README 完整
```

---

# 9. 部署需求

初级版要求：

```text
Docker 可启动
Docker Compose 可启动
健康检查可用
日志可查看
Swagger 可访问
```

推荐服务：

```text
FastAPI
PostgreSQL
Qdrant
Redis
```

最小部署：

```bash
docker compose up -d
```

启动后可访问：

```text
http://localhost:8000/docs
http://localhost:8000/health
```

---

# 10. 初级项目验收标准

项目完成以下功能，才算初级合格：

```text
1. 用户可以上传 PDF / Markdown / TXT
2. 系统能解析文档
3. 系统能清洗文本
4. 系统能切片
5. 系统能生成 Embedding
6. 系统能存入向量库
7. 用户可以提问
8. 系统能检索相关片段
9. 系统能基于知识库回答
10. 回答能返回引用来源
11. 支持多轮对话
12. 支持查询订单
13. 支持查询物流
14. 支持转人工
15. 工具调用失败有处理
16. 有日志记录
17. 有 Swagger 文档
18. 有健康检查
19. Docker 可启动
20. 有 README 和架构图
```

---

