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

## Milestone 6 — Review Console (web dashboard)
- **Status:** Not started in this repo. No commits, no branches (`git ls-remote` shows only `main`), no open PRs, nothing uncommitted locally.
- **Where the work actually is:** Being specified with Codex via ChatGPT (shared thread: `chatgpt.com/share/6a509bd8-7e2c-83ea-88ff-6cdcb5ef88d2`), targeting a server-rendered Jinja2 dashboard (per that thread — "local Jinja dashboard," not a separate frontend framework). As of the last visible message in that thread, Codex had produced a design and stopped at an approval gate ("The design is ready for approval. Please confirm...") rather than implementing.
- **Do not mark this done** until it shows up as commits/a PR against `yaja95/evalops-dashboard`, verified the same way as milestones 0–5 above — a "Codex says it's finished" or "ChatGPT summarized it as complete" report is not sufficient. See [PM_PROTOCOL.md](PM_PROTOCOL.md).
