# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

## Commands

```bash
uv sync                                                          # install dependencies
uv run alembic upgrade head                                      # apply migrations (required before first run)
uv run uvicorn --app-dir src evalops_dashboard.main:app --reload # run the API (http://127.0.0.1:8000/docs)
uv run ruff format .                                              # format
uv run ruff check .                                               # lint
uv run pytest                                                     # run all tests
uv run pytest tests/test_comparison.py                            # run a single test file
uv run pytest tests/test_comparison.py::test_name -v               # run a single test
```

CI (`.github/workflows/ci.yml`) runs `ruff format --check`, `ruff check`, `alembic upgrade head`, then `pytest` — run all four before finishing a change.

Database URL is configurable via `EVALOPS_DATABASE_URL` (defaults to `sqlite:///./evalops.db`); CI uses a separate `ci_evalops.db`.

## Architecture

FastAPI + SQLModel app under `src/evalops_dashboard/`, with routers mounted onto `main.py`:

- `models.py` — all SQLModel table models plus their `*Create`/`*Read` DTOs live in one file. Table models (`Prompt`, `ModelResponse`, `Rubric`, `RubricCriterion`, `Evaluation`, `CriterionScore`) and their API-facing schemas are colocated here; there's no separate schemas package.
- `database.py` — single SQLAlchemy `engine`, built from `EVALOPS_DATABASE_URL`. Uses `StaticPool` only for the in-memory `sqlite://` test case, and enables SQLite foreign keys via a `connect` event listener.
- `main.py` — app instance, lifespan hook that seeds demo data on startup via `seed.py` (the app never creates/alters tables at runtime — schema changes only happen through Alembic), and the `/health`, `/analytics/summary`, `/prompts`, `/responses` routes directly.
- `routers/` — `evaluations.py`, `rubrics.py`, `comparisons.py` hold the remaining route groups, each taking a `SessionDep` (`Annotated[Session, Depends(get_session)]`).
- `scoring.py` — pure functions for weighted overall-score and pass/fail calculation used by the evaluations router; formula and pass rules are documented in the README's "Evaluation Scoring" section.
- `comparison.py` — pure aggregation logic for the `/prompts/{id}/comparison` endpoint (ranking, tie-breakers, `comparison_ready`/`winner_response_id` derivation). `routers/comparisons.py` loads the ORM rows, converts them into this module's plain dataclasses, calls `build_comparison_summary`, then maps the result back onto the `PromptComparisonRead` response model. When changing comparison behavior, the ranking/aggregation logic belongs in `comparison.py`, not the router.

This split (pure calculation module + thin router that does ORM I/O and DTO mapping) is the pattern to follow for new score- or ranking-related features — see `scoring.py`/`evaluations.py` and `comparison.py`/`comparisons.py` as the two existing examples.

- `routers/dashboard.py` — server-rendered HTML routes under `/dashboard` (Jinja2 templates in `templates/`, static assets in `static/`, mounted via `StaticFiles` at `/static` in `main.py`). This one has no pure-calculation counterpart: it's read-only presentation over existing data, and reuses `build_rubric_response` (from `rubrics.py`), `build_evaluation_responses` (from `evaluations.py`), and `compare_prompt_responses` (from `comparisons.py`, called directly rather than re-deriving its aggregation) rather than introducing new business logic. Prompt/response queries have no existing builder either, so those are inlined directly in the route functions. `build_applicable_rubrics` and `build_chart_rows` (with the `BarChartRow`/`CriterionChart`/`ChartData` dataclasses) also live here — the latter is presentation reshaping (rounding, percentage-of-max math for bar widths) on top of `compare_prompt_responses`'s output, not aggregation, which is why it stays out of `comparison.py`. Charts themselves are static server-rendered bars (a `bar_chart` Jinja macro in `templates/partials/bar_chart.html`) with no client-side JavaScript, consistent with the rest of the dashboard.

### Migrations

Schema changes go through Alembic (`alembic/versions/`), not app startup. `alembic/env.py` imports `evalops_dashboard.models` for autogenerate metadata and reads `EVALOPS_DATABASE_URL` the same way the app does. Breaking migrations (see the `20260710_0002` migration) are acceptable pre-release but must be called out in the README's Database Migrations section, including what data they reset vs. preserve.

## Roadmap

The README's "Future Roadmap" section is the current backlog: CSV import/export, model/provider metadata + cost tracking, cross-rubric analytics, auth, and Postgres support.
