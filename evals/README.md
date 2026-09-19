# 评测运行说明

`cases.json` 是与 PRD 验收标准对应的场景清单。若要生成可重复、可追溯的真实评分报告，先用采集脚本记录接口实际返回结果，再执行评分：

```powershell
$env:DEMO_API_KEY = "你的 API Key"
.\.venv\Scripts\python.exe -m evals.collect_predictions --input evals\scenarios.example.jsonl --output evals\predictions.jsonl
```

采集脚本会调用 `GET /api/v1/users/me`、创建独立会话并调用 `POST /api/v1/chat`，自动写入实际回答、引用、服务端 `latency_ms` 与端到端 `observed_latency_ms`。不会把 API Key 写入输入或输出文件。请将示例场景复制到私有文件后按自己的已入库语料修改预期答案与来源。

随后运行：

```powershell
.\.venv\Scripts\python.exe -m evals.run_evaluation --input evals\predictions.jsonl --output evals\reports\latest.json
```

该命令会同时生成 `evals/reports/latest.json`（机器可读）和 `evals/reports/latest.md`（便于面试展示和人工审查）。评测输入、报告目录均默认不提交 Git，避免写入客户问题、答案或引用内容。

每一行 `answer`（回答评测）记录必须包含以下字段：

- `id`：评测用例编号。
- `kind`：固定为 `answer`。
- `question`：用户问题。
- `expected_answer`：预期答案。
- `expected_source`：预期来源。
- `prediction`：系统实际回答。
- `predicted_sources`：系统实际返回的来源列表。
- `latency_ms`：接口响应中的服务端耗时，单位毫秒，必填。
- `observed_latency_ms`：从发起 HTTP 请求到收到完整响应的端到端耗时，单位毫秒，可选。

每一行 `tool`（工具调用评测）记录必须包含以下字段：

- `id`：评测用例编号。
- `kind`：固定为 `tool`。
- `question`：用户问题。
- `expected_tool`：预期调用的工具名称。
- `expected_input`：预期工具参数。
- `predicted_tool`：实际调用的工具名称。
- `predicted_input`：实际工具参数。
- `latency_ms`：接口响应中的服务端耗时，单位毫秒，必填。
- `observed_latency_ms`：端到端耗时，单位毫秒，可选。

生成的报告会汇总回答正确性、来源正确性、幻觉率、完整性、工具选择正确性和工具参数正确性；还会分别统计服务端、端到端和评测模型耗时的最小值、均值、P50、P95、最大值。每条结果会包含评分理由、服务端耗时和评分耗时，报告也会记录评测模型的 token 用量。

## 建议采集方式

RAG 回答可直接使用采集脚本。工具用例请从真实 `POST /api/v1/chat` 响应和管理员工具审计记录中导出 `predicted_tool`、`predicted_input` 与实际 `latency_ms`；当前聊天响应基于最小权限原则只返回工具摘要，不返回工具参数。不要编写或手填“通过”的预测结果；只有真实接口响应才具有评测价值。
