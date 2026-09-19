# Evaluation runner

`cases.json` is the PRD acceptance checklist. For repeatable scored runs, record API responses as JSONL and execute:

```powershell
.\.venv\Scripts\python.exe -m evals.run_evaluation --input evals\predictions.jsonl --output evals\reports\latest.json
```

Each `answer` row requires `id`, `kind`, `question`, `expected_answer`, `expected_source`, `prediction`, and `predicted_sources`. Each `tool` row requires `id`, `kind`, `question`, `expected_tool`, `expected_input`, `predicted_tool`, and `predicted_input`.

The report contains correctness, source correctness, hallucination rate, completeness, tool selection correctness, and tool argument correctness. Do not commit captured customer data or generated reports.
