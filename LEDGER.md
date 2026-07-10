# LEDGER.md

Running record of what has actually shipped in `evalops-dashboard`, verified against `git log` / `gh pr list`, not against completion reports. See [PM_PROTOCOL.md](PM_PROTOCOL.md) for how this file is maintained.

Numbering below follows commit order on `main`. If you've been using different milestone numbers with Codex/ChatGPT, say so and this file will be renumbered to match — don't silently assume the two line up.

## Milestone 0 — Initial scaffold
- **Status:** Done
- **Merged:** 2026-07-09, commit `acf0d67`, direct to `main` (no PR)
- **Shipped:** FastAPI app skeleton, `/health` endpoint, initial project layout (`src/evalops_dashboard/`).

## Milestone 1 — Rubric analytics summary
- **Status:** Done
- **Merged:** 2026-07-09, commit `0e0e03b`, direct to `main` (no PR)
- **Shipped:** `/analytics/summary` endpoint (prompt/response/evaluation counts, average score, pass rate).

## Milestone 2 — Reusable rubric templates
- **Status:** Done
- **Merged:** 2026-07-09, commit `f1ef01e`, direct to `main` (no PR)
- **Shipped:** Rubric + rubric criterion models and create/list routes.

## Milestone 3 — Alembic migrations and isolated database tests
- **Status:** Done
- **Merged:** 2026-07-10, commit `2a5394c`, PR [#1](https://github.com/yaja95/evalops-dashboard/pull/1) (merged 04:08 UTC)
- **Shipped:** Alembic wired up (`alembic/`, baseline migration), `tests/conftest.py` test isolation.
- **Bug found & fixed:** *Fake rollback tests.* The first pass of `conftest.py` assumed the test DB was isolated without enforcing it. The merged version added a hard guard — `RuntimeError` if `engine.url` isn't in-memory SQLite — plus an `autouse` fixture that explicitly `drop_all`/`create_all`s around every test, per the PR's second commit ("Harden test database isolation"). This is the reference case for the "fake rollback tests" bug class in [PM_PROTOCOL.md](PM_PROTOCOL.md).

## Milestone 4 — Rubric-driven evaluations
- **Status:** Done
- **Merged:** 2026-07-10, commit `f9d69b8`, PR [#2](https://github.com/yaja95/evalops-dashboard/pull/2) (merged 04:54 UTC)
- **Shipped:** Criterion-level scoring (`scoring.py`), `Evaluation`/`CriterionScore` models, weighted overall-score + pass/fail calculation, breaking migration `20260710_0002` (replaces fixed-column evaluations; existing evaluation rows reset, prompts/responses/rubrics preserved — documented in README).
- **Bug found & fixed:** Scoring boundary condition and SQLite foreign-key listener scope, per the PR's second commit ("Fix scoring boundary and SQLite listener scope"). Not independently diffed in detail; flagged here for visibility, not asserted with the same confidence as the two bugs below.

## Milestone 5 — Model response comparison
- **Status:** Done
- **Merged:** 2026-07-10, commit `266335d`, PR [#3](https://github.com/yaja95/evalops-dashboard/pull/3) (merged 05:30 UTC)
- **Shipped:** `GET /prompts/{id}/comparison`, ranking with deterministic tie-breakers, `comparison.py` pure aggregation module.
- **Bug found & fixed:** *Rounding-before-decision.* The PR's first commit ranked responses using the rounded, display-facing `average_overall_score`/`pass_rate`. The second commit ("Rank comparisons with raw aggregate values") introduced `raw_average_overall_score`/`raw_pass_rate` fields and switched ranking to use those instead, so tie-breaking isn't distorted by rounding. This is the reference case for the "rounding-before-decision" bug class in [PM_PROTOCOL.md](PM_PROTOCOL.md).

## Milestone 6 — Web Dashboard
- **Status:** In progress — implemented on `feature/web-dashboard`, pushed to GitHub, not yet merged. Not marked Done until merged and independently re-verified per [PM_PROTOCOL.md](PM_PROTOCOL.md).
- **Implementation:** Server-rendered Jinja2 dashboard under `/dashboard` (landing page + list/detail views for prompts, model responses, rubrics, evaluations). Read-only: no create/edit forms, no comparison charts (next milestone). Reuses `build_rubric_response`/`build_evaluation_responses` rather than duplicating query logic. 85/85 tests passing (15 new), verified end-to-end in a real browser against seeded data, including the empty-state and pass/fail badge cases.
- **Two competing implementations discovered and resolved (2026-07-10):** Codex had *also* been building a dashboard, independently, in a separate local clone at `~/Documents/Codex/2026-07-09/explore/evalops-dashboard` on a local-only branch `feature/evalops-review-console` (commits `cb81de5`, `5b1422c`, never pushed to GitHub) — a client-side JS "Review Console" with filter dropdowns, at the time of discovery stuck on "Loading review data...". This wasn't visible from the tracked repo or the ChatGPT thread (`chatgpt.com/share/6a509bd8-7e2c-83ea-88ff-6cdcb5ef88d2`), which only showed Codex stopped at a design-approval gate — it had evidently continued elsewhere. User chose to proceed with the Claude Code / `feature/web-dashboard` implementation; the Codex Review Console directory is not part of this repo's history and was left untouched.
