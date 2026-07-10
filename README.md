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
- Alembic-managed SQLite schema migrations
- Seed data for a sample support-triage evaluation
- Prompt records
- Model response records
- Rubric-based evaluation records with instruction following, truthfulness, completeness, conciseness, safety, writing style, and overall scores
- Reusable rubric templates with weighted criteria for future evaluation scoring workflows
- Analytics summary for counts, average scores, most common failure category, and pass rate
- Basic create/list API routes
- Test coverage for health and seeded data

## Local Setup

Install dependencies:

```bash
uv sync
```

Initialize or update your local database:

```bash
uv run alembic upgrade head
```

Run the API:

```bash
uv run uvicorn --app-dir src evalops_dashboard.main:app --reload
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

## Database Migrations

This project uses Alembic for database schema changes. The app no longer creates or modifies tables during startup; startup only seeds demo data after the database schema already exists.

For a new local database:

```bash
uv run alembic upgrade head
uv run uvicorn --app-dir src evalops_dashboard.main:app --reload
```

For future schema changes:

```bash
uv run alembic upgrade head
```

If your local `evalops.db` was created by an older pre-migration version of the app, this pre-release portfolio project may be easiest to reset by backing up and removing the old database, then applying the baseline migration:

```bash
cp evalops.db evalops.db.backup
rm evalops.db
uv run alembic upgrade head
```

Do not use `alembic stamp head` unless you have manually verified that the existing database schema exactly matches the migration history.

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

Create an evaluation:

```bash
curl -X POST http://127.0.0.1:8000/evaluations \
  -H "Content-Type: application/json" \
  -d '{
    "response_id": 1,
    "rubric_name": "Support urgency rubric v1",
    "instruction_following_score": 5,
    "truthfulness_score": 5,
    "completeness_score": 4,
    "conciseness_score": 4,
    "safety_score": 5,
    "writing_style_score": 4,
    "overall_score": 5,
    "failure_category": null,
    "justification": "Correctly identifies production downtime and recommends escalation.",
    "evaluator": "ajay"
  }'
```

Create a reusable rubric template:

```bash
curl -X POST http://127.0.0.1:8000/rubrics \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Support Response Quality",
    "version": 1,
    "description": "Evaluates customer-support responses.",
    "pass_threshold": 4,
    "criteria": [
      {
        "name": "Instruction Following",
        "description": "The response addresses the requested task.",
        "weight": 2,
        "min_score": 1,
        "max_score": 5,
        "required": true
      },
      {
        "name": "Clarity",
        "description": "The response is clear and understandable.",
        "weight": 1,
        "min_score": 1,
        "max_score": 5,
        "required": true
      }
    ]
  }'
```

Rubric templates define the criteria and weights that future evaluation workflows will use. Per-criterion evaluation scoring is the next planned feature.

Get an analytics summary:

```bash
curl http://127.0.0.1:8000/analytics/summary
```

Example response:

```json
{
  "prompt_count": 3,
  "response_count": 6,
  "evaluation_count": 6,
  "average_overall_score": 4.2,
  "average_truthfulness_score": 4.0,
  "most_common_failure_category": "unsupported_claim",
  "pass_rate": 0.83
}
```

## Project Structure

```text
evalops-dashboard/
  .github/workflows/ci.yml
  alembic/
    env.py
    script.py.mako
    versions/
      20260710_0001_initial_schema.py
  alembic.ini
  src/evalops_dashboard/
    routers/
      __init__.py
      rubrics.py
    __init__.py
    database.py
    main.py
    models.py
    seed.py
  tests/
    conftest.py
    test_app.py
    test_migrations.py
    test_rubrics.py
  AGENTS.md
  pyproject.toml
  README.md
```

## Future Roadmap

- Add a simple web dashboard for browsing prompts, responses, and evaluations.
- Add per-criterion scoring that applies rubric templates to model responses.
- Add CSV import/export for evaluation batches.
- Add model/provider metadata and cost tracking.
- Add authentication for internal team usage.
- Add PostgreSQL support for deployed environments.
- Add charts for pass rate, average score, and model comparison.
