# 评测运行说明

`cases.json` 是与 PRD 验收标准对应的场景清单。若要生成可重复、可追溯的评分报告，先将接口实际返回结果记录为 JSONL 文件，再执行：

```powershell
.\.venv\Scripts\python.exe -m evals.run_evaluation --input evals\predictions.jsonl --output evals\reports\latest.json
```

每一行 `answer`（回答评测）记录必须包含以下字段：

- `id`：评测用例编号。
- `kind`：固定为 `answer`。
- `question`：用户问题。
- `expected_answer`：预期答案。
- `expected_source`：预期来源。
- `prediction`：系统实际回答。
- `predicted_sources`：系统实际返回的来源列表。

每一行 `tool`（工具调用评测）记录必须包含以下字段：

- `id`：评测用例编号。
- `kind`：固定为 `tool`。
- `question`：用户问题。
- `expected_tool`：预期调用的工具名称。
- `expected_input`：预期工具参数。
- `predicted_tool`：实际调用的工具名称。
- `predicted_input`：实际工具参数。

生成的报告会汇总回答正确性、来源正确性、幻觉率、完整性、工具选择正确性和工具参数正确性。不要提交包含客户数据的评测输入或生成报告。
