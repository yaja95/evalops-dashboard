# evalops-dashboard

`evalops-dashboard` is a lightweight AI evaluation operations API for storing prompts, model responses, reusable rubrics, and auditable criterion-level evaluations.

## Business Problem

Teams experimenting with AI often collect prompts, outputs, and quality judgments in scattered spreadsheets or chat threads. That makes it hard to compare model behavior, audit decisions, or understand whether changes are improving quality.

This project provides a small operational foundation for evaluation workflows: capture the prompt, capture the model response, apply a reusable rubric, calculate server-controlled results, and make the records available through a simple API.

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
- Reusable rubric templates with weighted criteria
- Rubric-driven evaluations with criterion-level score records
- Server-calculated weighted overall scores and pass/fail results
- Analytics summary for counts, average overall score, and pass rate
- Basic create/list API routes
- Behavioral test coverage for scoring, validation, migrations, and seeded data

## Business Value

- Consistent scoring through reusable evaluation policies.
- Auditable criterion-level judgments instead of opaque overall scores.
- Server-controlled results so clients cannot submit their own pass/fail outcome.
- Model-response comparison readiness once multiple responses are evaluated with the same rubric.

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

The `20260710_0002` migration is a breaking pre-release migration. It replaces the old fixed-column evaluation schema with rubric-driven evaluations and criterion-score records. Existing evaluation rows are reset during the migration; prompts, model responses, rubrics, and rubric criteria are preserved. Downgrading restores the previous schema shape but does not restore deleted evaluation rows.

## Evaluation Scoring

Evaluations are created against an existing model response and an existing rubric. Clients submit exactly one score for each criterion in that rubric. The API validates the scores, calculates the weighted result, and stores the calculated outcome.

Formula:

```text
sum(score * criterion weight) / sum(criterion weights)
```

The stored `overall_score` is rounded to two decimal places.

An evaluation passes only when:

- The weighted overall score is greater than or equal to the rubric `pass_threshold`.
- Every required criterion has a score greater than or equal to the rubric `pass_threshold`.

A non-required criterion may fall below the threshold if the weighted overall score still passes.

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
    "rubric_id": 1,
    "justification": "The response followed the task and was accurate.",
    "evaluator": "ajay",
    "scores": [
      {
        "criterion_id": 1,
        "score": 5,
        "notes": "Directly answered the request."
      },
      {
        "criterion_id": 2,
        "score": 4,
        "notes": "Accurate with minor room for clarification."
      }
    ]
  }'
```

Representative response:

```json
{
  "id": 1,
  "response_id": 1,
  "rubric_id": 1,
  "rubric_name": "Support Response Quality",
  "rubric_version": 1,
  "overall_score": 4.67,
  "passed": true,
  "justification": "The response followed the task and was accurate.",
  "evaluator": "ajay",
  "created_at": "2026-07-10T12:00:00",
  "scores": [
    {
      "criterion_id": 1,
      "criterion_name": "Instruction Following",
      "score": 5,
      "weight": 2,
      "required": true,
      "notes": "Directly answered the request."
    },
    {
      "criterion_id": 2,
      "criterion_name": "Accuracy",
      "score": 4,
      "weight": 1,
      "required": true,
      "notes": "Accurate with minor room for clarification."
    }
  ]
}
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

Rubric templates define the criteria and weights that evaluation workflows use.

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
      20260710_0002_rubric_driven_evaluations.py
  alembic.ini
  src/evalops_dashboard/
    routers/
      __init__.py
      evaluations.py
      rubrics.py
    __init__.py
    database.py
    main.py
    models.py
    scoring.py
    seed.py
  tests/
    conftest.py
    test_app.py
    test_evaluations.py
    test_migrations.py
    test_rubrics.py
    test_scoring.py
  AGENTS.md
  pyproject.toml
  README.md
```

## Future Roadmap

- Add a simple web dashboard for browsing prompts, responses, and evaluations.
- Add generic per-criterion analytics across rubrics and models.
- Add CSV import/export for evaluation batches.
- Add model/provider metadata and cost tracking.
- Add authentication for internal team usage.
- Add PostgreSQL support for deployed environments.
- Add charts for pass rate, average score, and model comparison.
