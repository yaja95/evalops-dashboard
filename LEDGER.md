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
- **Status:** Done
- **Merged:** 2026-07-10T20:18:12Z, squash commit [`648ac7e`](https://github.com/yaja95/evalops-dashboard/commit/648ac7eb2e3e584ef6c840e14f5b3728c435868d) on `main`, PR [#4](https://github.com/yaja95/evalops-dashboard/pull/4). Verified via `gh pr view 4` (state MERGED) and `git log`/`git ls-remote` against `origin/main` directly — not taken on the completion report alone.
- **Post-merge checks re-run against `main` (not assumed from before merge):** `ruff format --check .`, `ruff check .`, `alembic upgrade head`, `pytest` — all pass, 85/85 tests.
- **Shipped:** Server-rendered Jinja2 dashboard under `/dashboard` (landing page + list/detail views for prompts, model responses, rubrics, evaluations). Read-only: no create/edit forms, no comparison charts (next milestone). Reuses `build_rubric_response`/`build_evaluation_responses` rather than duplicating query logic. Verified end-to-end in a real browser against seeded data pre-merge, including the empty-state and pass/fail badge cases.
- **Two competing implementations discovered and resolved (2026-07-10):** Codex had *also* been building a dashboard, independently, in a separate local clone at `~/Documents/Codex/2026-07-09/explore/evalops-dashboard` on a local-only branch `feature/evalops-review-console` (commits `cb81de5`, `5b1422c`, never pushed to GitHub) — a client-side JS "Review Console" with filter dropdowns, at the time of discovery stuck on "Loading review data...". This wasn't visible from the tracked repo or the ChatGPT thread (`chatgpt.com/share/6a509bd8-7e2c-83ea-88ff-6cdcb5ef88d2`), which only showed Codex stopped at a design-approval gate — it had evidently continued elsewhere. User chose to proceed with the Claude Code / `feature/web-dashboard` implementation; the Codex Review Console directory is not part of this repo's history and was left untouched.
- **Commit hygiene:** Branch commits were rewritten before merge to drop `Co-Authored-By` AI trailers (repo is a forward-facing portfolio project). Final squash commit author is `Ajay Williams` only, no AI attribution anywhere in the merged history or PR body.

## Milestone 7 — Comparison Charts on the Web Dashboard
- **Status:** Done
- **Merged:** 2026-07-10T22:30:47Z, squash commit [`57b6021`](https://github.com/yaja95/evalops-dashboard/commit/57b602158176c7582df62a72951fc69ca4a95111) on `main`, PR [#5](https://github.com/yaja95/evalops-dashboard/pull/5). Verified via `gh pr list --state merged` and `git log`/`git ls-remote` against `origin/main` directly.
- **Post-merge checks re-run against `main`:** `ruff format --check .`, `ruff check .`, `alembic upgrade head`, `pytest` — all pass, 94/94 tests.
- **Shipped:** `/dashboard/prompts/{id}/comparison` — static, server-rendered bar charts (quality, pass rate, criterion performance, latency) for a prompt's model responses under a selected rubric. No client-side JavaScript, by design (chosen over a Chart.js/CDN approach to keep the dashboard's zero-JS foundation, with interactivity explicitly deferred). Reuses `compare_prompt_responses` from `routers/comparisons.py` directly rather than duplicating aggregation/ranking logic; new `build_applicable_rubrics`/`build_chart_rows` helpers in `dashboard.py` handle rubric discovery (no `Prompt`→`Rubric` link table exists, so applicability is derived transitively through `Evaluation`/`ModelResponse`) and presentation-only percentage math.
- **Bug found & fixed (pre-merge, caught by manual browser verification, not by tests):** The "Winner" badge lived inside the same `text-overflow: ellipsis`-truncated `<span>` as the model name, so it was silently clipped whenever the label overflowed — invisible in the rendered page despite being present in the HTML and passing all automated tests (which only assert byte-presence in `response.text`, not visual layout). Fixed by splitting the truncated label text into its own span. Reference case for why layout/visibility bugs need actual browser verification, not just HTML-content assertions — automated tests alone would have shipped this silently broken.
- **Commit hygiene:** No AI trailers on branch commits (following the convention established in Milestone 6). Merged via GitHub's default squash body (concatenated commit messages) rather than the custom description drafted for it — still no AI attribution anywhere, just not the exact suggested text.

## Milestone 8 — CSV Import/Export for Evaluation Batches
- **Status:** Done
- **Merged:** 2026-07-10T23:06:58Z, squash commit [`080c265`](https://github.com/yaja95/evalops-dashboard/commit/080c265958de95fe04802c5902a41a3a9fe0f28d) on `main`, PR [#6](https://github.com/yaja95/evalops-dashboard/pull/6). Verified via `gh pr list --state merged` and `git log`/`git ls-remote` against `origin/main` directly.
- **Post-merge checks re-run against `main`:** `ruff format --check .`, `ruff check .`, `alembic upgrade head`, `pytest` — all pass, 107/107 tests.
- **Shipped:** `GET /evaluations/export?rubric_id={id}` and `POST /evaluations/import?rubric_id={id}`, each scoped to one rubric (round-trippable column layout: `response_id, evaluator, justification`, then `<criterion name>_score`/`_notes` per criterion). Import is partial-success with per-row error reporting — row errors reuse the exact validation messages `POST /evaluations` already produces. `create_evaluation` was refactored into a reusable `create_evaluation_from_payload` core shared by the single-create route and the import loop, so validation/scoring/persistence logic lives in one place. Re-importing a previously exported CSV creates new records rather than deduping, matching existing `POST /evaluations` behavior. Dashboard gets one "Export CSV" link on the rubric detail page — no import form, keeping the browsing-only boundary from Milestones 6/7 intact.
- **Bug found & fixed (caught during test-writing, not planning):** the first cut of the per-row integer-parsing error surfaced a bare Python exception message (`"invalid literal for int() with base 10: 'not-a-number'"`) with no indication of which field failed. Fixed with a `parse_row_int` helper that names the criterion (`"Score for 'Instruction Following' must be an integer."`), matching the clear-error-message convention already used by `validate_submitted_scores` elsewhere in the codebase. Minor relative to the other bug classes, but a reminder that reusing stdlib exceptions verbatim in user-facing error paths is itself worth checking for.
- **Commit hygiene:** No AI trailers, author is `Ajay Williams` only.
