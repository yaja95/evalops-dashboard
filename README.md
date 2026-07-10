# evalops-dashboard

`evalops-dashboard` is a lightweight AI evaluation operations API for storing prompts, model responses, and rubric-based evaluations.

## Business Problem

Teams experimenting with AI often collect prompts, outputs, and quality judgments in scattered spreadsheets or chat threads. That makes it hard to compare model behavior, audit decisions, or understand whether changes are improving quality.

This project provides a small operational foundation for evaluation workflows: capture the prompt, capture the model response, evaluate it against a rubric, and make the records available through a simple API.

## User

The first user is an AI product or operations team that needs a practical way to track prompt experiments and evaluation results before investing in a larger internal platform.

## Tech Stack

- Python 3.14
- FastAPI
- SQLModel
- SQLite
- uv
- pytest
- Ruff
- GitHub Actions CI

## Current Features

- `GET /health` health check
- SQLite schema creation on app startup
- Seed data for a sample support-triage evaluation
- Prompt records
- Model response records
- Rubric-based evaluation records
- Basic create/list API routes
- Test coverage for health and seeded data

## Local Setup

Install dependencies:

```bash
uv sync
```

If you already ran `uv sync` before this project had packaging metadata, rerun it once:

```bash
uv sync --reinstall
```

Run the API:

```bash
uv run uvicorn evalops_dashboard.main:app --reload
```

Open:

- API docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

Run checks:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

## Example API Calls

Create a prompt:

```bash
curl -X POST http://127.0.0.1:8000/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Classify support ticket urgency",
    "content": "Classify this customer message as low, medium, or high urgency.",
    "use_case": "support triage",
    "owner": "evalops"
  }'
```

List evaluations:

```bash
curl http://127.0.0.1:8000/evaluations
```

## Project Structure

```text
evalops-dashboard/
  .github/workflows/ci.yml
  src/evalops_dashboard/
    __init__.py
    database.py
    main.py
    models.py
    seed.py
  tests/
    test_app.py
  AGENTS.md
  pyproject.toml
  README.md
```

## Future Roadmap

- Add a simple web dashboard for browsing prompts, responses, and evaluations.
- Add rubric templates and per-criterion scoring.
- Add CSV import/export for evaluation batches.
- Add model/provider metadata and cost tracking.
- Add authentication for internal team usage.
- Add PostgreSQL support for deployed environments.
- Add charts for pass rate, average score, and model comparison.
