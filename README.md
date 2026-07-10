# evalops-dashboard

`evalops-dashboard` is a lightweight AI evaluation operations API for storing prompts, model responses, reusable rubrics, and auditable criterion-level evaluations.

Current version: `0.7.0`

## Business Problem

Teams experimenting with AI often collect prompts, outputs, and quality judgments in scattered spreadsheets or chat threads. That makes it hard to compare model behavior, audit decisions, or understand whether changes are improving quality.

This project provides a small operational foundation for evaluation workflows: capture the prompt, capture the model response, apply a reusable rubric, calculate server-controlled results, and make the records available through a simple API.

Version `0.3.0` added read-only model-response comparison for teams deciding which model output is best for a selected prompt and exact rubric version. Version `0.4.0` added a read-only web dashboard for browsing that data without hand-writing API calls. Version `0.5.0` added comparison charts to the dashboard so that comparison is visual, not just tabular. Version `0.6.0` added CSV import/export for evaluation batches, so a team can score a batch of responses in a spreadsheet instead of one API call at a time. Version `0.7.0` adds a model-pricing catalog and server-calculated cost tracking for model responses, so token usage translates into dollar cost without trusting a client-submitted figure.

## User

The first user is an AI product or operations team that needs a practical way to track prompt experiments and evaluation results before investing in a larger internal platform.

## Tech Stack

- Python 3.14
- FastAPI
- SQLModel
- Jinja2
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
- Read-only model-response comparison by prompt and exact rubric
- Server-calculated weighted overall scores and pass/fail results
- Analytics summary for counts, average overall score, and pass rate
- Basic create/list API routes
- Server-rendered web dashboard for browsing prompts, responses, rubrics, and evaluations (`/dashboard`)
- Comparison charts on the dashboard (quality, pass rate, criterion performance, latency) with rubric selection, built as static server-rendered bar charts with no client-side JavaScript
- CSV export/import for evaluation batches, scoped to one rubric per file, with per-row error reporting on import
- Model-pricing catalog (provider + model, price per 1k input/output tokens) with server-calculated cost per model response
- Behavioral test coverage for scoring, validation, migrations, comparisons, the dashboard, cost tracking, and seeded data

## Business Value

- Consistent scoring through reusable evaluation policies.
- Auditable criterion-level judgments instead of opaque overall scores.
- Server-controlled results so clients cannot submit their own pass/fail outcome.
- Model selection using comparable rubric-based quality signals.
- Prompt and model experimentation with quality-versus-latency tradeoffs.
- Multi-rater aggregation across multiple evaluations for the same response.
- Identification of evaluation coverage gaps through unscored response reporting.
- Server-calculated cost from a known pricing catalog, so clients cannot submit their own dollar figures — the same server-controlled-results principle already applied to pass/fail outcomes.

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

Version `0.3.0` adds a read-only aggregation endpoint and requires no new Alembic migration beyond the existing `head`.

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

## Cost Tracking

This app doesn't call LLMs itself, so it can't know token usage — clients submit `input_tokens`/`output_tokens` as raw facts when creating a model response. The dollar cost is then server-calculated from a `model-pricing` catalog entry matching that response's `(provider, model_name)`, the same way `overall_score`/`passed` are calculated from submitted criterion scores rather than trusted as client input. A client cannot submit `cost_usd` directly — the field isn't accepted on `POST /responses`.

Formula:

```text
(input_tokens / 1000) * input_price_per_1k_tokens + (output_tokens / 1000) * output_price_per_1k_tokens
```

The stored `cost_usd` is rounded to six decimal places, calculated once at response-creation time (not recalculated later if pricing changes).

If no `model-pricing` entry matches the response's provider/model, or if token counts weren't provided, `cost_usd` is simply `null` — this is a normal, expected case, not an error.

Create a pricing entry:

```bash
curl -X POST http://127.0.0.1:8000/model-pricing \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai-example",
    "model_name": "gpt-example-ops",
    "input_price_per_1k_tokens": 0.01,
    "output_price_per_1k_tokens": 0.03
  }'
```

Create a response with token usage:

```bash
curl -X POST http://127.0.0.1:8000/responses \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_id": 1,
    "model_name": "gpt-example-ops",
    "response_text": "High urgency...",
    "provider": "openai-example",
    "input_tokens": 1200,
    "output_tokens": 340
  }'
```

The response includes the calculated cost:

```json
{
  "id": 1,
  "model_name": "gpt-example-ops",
  "provider": "openai-example",
  "input_tokens": 1200,
  "output_tokens": 340,
  "cost_usd": 0.0222
}
```

## Model Response Comparison

Decision-makers often evaluate several model responses for the same prompt. Individual evaluations answer whether one response passed, but comparison answers which response performed best, which response passed most consistently, how each response performed by criterion, and which responses still need evaluation.

Endpoint:

```text
GET /prompts/{prompt_id}/comparison?rubric_id={rubric_id}
```

The `rubric_id` query parameter is required. A rubric ID identifies one exact rubric record and version, so comparisons never mix different rubric versions or criteria definitions.

The endpoint aggregates all evaluations for each prompt response that use the selected rubric. It does not select only the latest evaluation. This supports multi-rater workflows and reduces dependence on a single evaluator.

Ranking uses deterministic tie-breakers:

1. Higher average stored overall score
2. Higher pass rate from stored `passed` values
3. Lower measured `latency_ms`
4. Missing latency after measured latency
5. Lower `response_id`

`comparison_ready` is `true` only when at least two responses have matching evaluations under the selected rubric. `winner_response_id` is the first-ranked response only when comparison is ready; otherwise it is `null`. `unscored_response_ids` lists prompt responses that do not yet have an evaluation under the selected rubric.

## Web Dashboard

A read-only, server-rendered dashboard (Jinja2 templates, no JavaScript framework) for browsing the same data the API exposes:

- `/dashboard` — landing page with entity counts
- `/dashboard/prompts`, `/dashboard/prompts/{id}` — prompt list and detail (with its model responses)
- `/dashboard/responses`, `/dashboard/responses/{id}` — model response list and detail (with its evaluations, provider, token counts, and calculated cost)
- `/dashboard/rubrics`, `/dashboard/rubrics/{id}` — rubric list and detail (with its criteria)
- `/dashboard/evaluations`, `/dashboard/evaluations/{id}` — evaluation list and detail (with per-criterion scores)
- `/dashboard/prompts/{id}/comparison` — comparison charts (quality, pass rate, criterion performance, latency) for a prompt's model responses under a selected rubric, visualizing `GET /prompts/{id}/comparison`. If a prompt has evaluations under more than one rubric, a plain HTML form lets you pick which one; with exactly one applicable rubric it's auto-selected. Charts are static server-rendered bars (widths computed server-side, no client-side JavaScript) — consistent with the rest of the dashboard.

The rubric detail page includes an Export CSV link (`GET /evaluations/export?rubric_id={id}`) for downloading that rubric's evaluations.

This is still browsing-only: there are no create/edit forms. Use the JSON API above for writes.

## CSV Import/Export

Each CSV is scoped to **one rubric**, so column names are fixed for that rubric's criteria: `response_id, evaluator, justification`, then `<criterion name>_score, <criterion name>_notes` per criterion in rubric order. For example, exporting rubric 1 ("Support Response Quality", criteria Instruction Following / Operational Accuracy / Clarity) produces:

```text
response_id,evaluator,justification,Instruction Following_score,Instruction Following_notes,Operational Accuracy_score,Operational Accuracy_notes,Clarity_score,Clarity_notes
```

This makes export/import round-trippable: export a rubric's evaluations, edit scores in a spreadsheet, re-import.

Export:

```bash
curl -o evaluations.csv "http://127.0.0.1:8000/evaluations/export?rubric_id=1"
```

A rubric with zero evaluations exports a header-only CSV, not an error.

Import:

```bash
curl -X POST "http://127.0.0.1:8000/evaluations/import?rubric_id=1" \
  -F "file=@evaluations.csv"
```

Import is **partial-success**: each row is validated and persisted independently, so one bad row doesn't block the rest of the batch. The response reports what happened:

```json
{
  "created_count": 2,
  "errors": [
    {"row": 3, "detail": "Score for 'Clarity' must be no greater than 5."}
  ]
}
```

`row` is 1-indexed from the first data row (the row directly after the header). Row-level validation errors reuse the exact same messages as `POST /evaluations` — a score out of a criterion's bounds produces the identical wording either way. A structural problem (missing or unexpected columns, meaning the CSV doesn't match the rubric's *current* criteria — for example if criteria changed since the file was exported) fails the whole import with a single 422, since no row can be meaningfully parsed in that case.

**Re-importing a previously exported CSV creates new evaluation records — it does not deduplicate.** This matches calling `POST /evaluations` directly, which nothing prevents you from doing twice with the same payload today.

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

Compare seeded model responses:

```bash
curl "http://127.0.0.1:8000/prompts/1/comparison?rubric_id=1"
```

Representative comparison response:

```json
{
  "prompt_id": 1,
  "prompt_title": "Classify support ticket urgency",
  "prompt_use_case": "support triage",
  "rubric": {
    "id": 1,
    "name": "Support Response Quality",
    "version": 1,
    "pass_threshold": 4
  },
  "response_count": 3,
  "compared_response_count": 2,
  "comparison_ready": true,
  "winner_response_id": 1,
  "unscored_response_ids": [3],
  "results": [
    {
      "rank": 1,
      "response_id": 1,
      "model_name": "gpt-example-ops",
      "response_text": "High urgency. The customer reports production downtime...",
      "latency_ms": 842,
      "evaluation_count": 1,
      "average_overall_score": 4.8,
      "pass_rate": 1.0,
      "latest_evaluated_at": "2026-07-10T12:00:00",
      "criterion_averages": [
        {
          "criterion_id": 1,
          "criterion_name": "Instruction Following",
          "weight": 2.0,
          "required": true,
          "average_score": 5.0
        }
      ]
    }
  ]
}
```

Seeded demo data now includes three responses for the support-triage prompt: two evaluated responses ranked by the comparison endpoint and one unevaluated draft response reported in `unscored_response_ids`.

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
      20260710_0003_model_pricing_and_cost_tracking.py
  alembic.ini
  src/evalops_dashboard/
    routers/
      __init__.py
      comparisons.py
      dashboard.py
      evaluations.py
      pricing.py
      rubrics.py
    static/
      dashboard.css
    templates/
      partials/
        bar_chart.html
        empty_state.html
      base.html
      evaluation_detail.html
      evaluations_list.html
      index.html
      prompt_comparison.html
      prompt_detail.html
      prompts_list.html
      response_detail.html
      responses_list.html
      rubric_detail.html
      rubrics_list.html
    __init__.py
    comparison.py
    cost.py
    database.py
    main.py
    models.py
    scoring.py
    seed.py
  tests/
    conftest.py
    test_app.py
    test_comparison.py
    test_comparisons.py
    test_cost.py
    test_dashboard.py
    test_dashboard_comparison.py
    test_evaluations.py
    test_evaluations_csv.py
    test_migrations.py
    test_model_responses.py
    test_pricing.py
    test_rubrics.py
    test_scoring.py
  AGENTS.md
  pyproject.toml
  README.md
```

## Future Roadmap

- Add generic per-criterion analytics across rubrics and models.
- Add authentication for internal team usage.
- Add PostgreSQL support for deployed environments.
