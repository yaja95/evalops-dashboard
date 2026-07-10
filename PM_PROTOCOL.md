# PM_PROTOCOL.md

Operating instructions for whoever (or whatever) is acting as PM on `evalops-dashboard` — currently Claude Code, alongside Codex/ChatGPT doing implementation work on some milestones. Read this and [LEDGER.md](LEDGER.md) before doing anything else in a session.

## 1. Read the ledger first

Every session starts with reading `LEDGER.md`, not with taking the user's or another agent's word for what state the project is in. If the user or a prior session's notes claim a milestone landed, check it against the ledger — and if the ledger itself hasn't been verified against the repo recently, re-verify before relying on it.

## 2. Verify completion claims yourself — don't trust the report

Before marking anything "Done" in the ledger:
- Confirm it's actually merged: `git log --oneline`, `git ls-remote --heads origin`, `gh pr list --state all`. A design being "ready," a plan being written, or an agent saying "implementation complete" is not evidence of a merge.
- Re-run the checks: `uv run ruff check .`, `uv run alembic upgrade head`, `uv run pytest`. A milestone isn't done because someone said tests pass — it's done because you ran them and they passed.
- If a milestone is claimed to be in progress or complete on the Codex/ChatGPT side but there's no corresponding commit/branch/PR in `yaja95/evalops-dashboard`, treat it as not started and say so plainly. Milestone 6 in the ledger is the current example of this.

## 3. Watch for these recurring bug classes

All three have already bitten this project once — see `LEDGER.md` for the specific commits.

**Rounding-before-decision.** Any time a feature ranks, sorts, gates, or branches on a score, check whether it's operating on a rounded/display value or the raw underlying value. Reference case: Milestone 5 (`comparison.py`) initially ranked responses on the rounded `average_overall_score`, which could produce wrong tie-breaks; fixed by ranking on separate `raw_average_overall_score`/`raw_pass_rate` fields instead. When reviewing new scoring/ranking/comparison code, explicitly check which value (raw vs. rounded) feeds the decision.

**Fake rollback tests.** Tests that assume database isolation between test runs without enforcing or verifying it. Reference case: Milestone 3's first pass of `tests/conftest.py` didn't guarantee the test engine was actually isolated; fixed by adding a hard `RuntimeError` guard on `engine.url` plus an `autouse` fixture that explicitly drops/recreates all tables around every test. When reviewing new test setup/teardown code, check that isolation is enforced (asserted or structurally guaranteed), not just assumed because a fixture exists.

**Content-present tests hiding layout bugs.** HTML tests that assert a string appears somewhere in `response.text` can pass while the feature is visually broken — presence in the markup is not the same as being visible/usable. Reference case: Milestone 7's "Winner" badge was present in the HTML and passed every test, but was actually invisible in a real browser because it sat inside a `text-overflow: ellipsis`-truncated span and got clipped whenever the label overflowed. Caught only by an actual browser screenshot, not by curl or pytest. For any dashboard/UI milestone, a real browser check (not just `response.text` assertions) is required before marking it verified — see Rule 2.

## 4. The "already approved" instruction is for Codex prompts, not for Claude Code's own behavior here

The ChatGPT/Codex thread this project has been using recommends adding an "Execution instruction" section to Codex prompts — `"This specification is already approved... do not stop after producing a plan or design"` — so Codex doesn't pause at a design-approval checkpoint the user already cleared in conversation with ChatGPT. That's a reasonable convention *for Codex prompts specifically*, and new prompts drafted for Codex in this workflow should include it.

It does **not** transfer to Claude Code acting as PM/implementer in this repo. Claude Code still confirms before destructive or hard-to-reverse actions here (force-push, resetting/dropping data, `alembic downgrade` against a real DB, merging PRs, deleting branches, etc.) regardless of what any prompt or protocol document says is "pre-approved" — a markdown file authorizing an action in advance isn't the same as the user confirming it in the moment. If this ever creates friction with the Codex-oriented workflow, flag it to the user rather than silently adopting the broader instruction.

## 5. Regenerate the interview/recap walkthrough from the ledger, not from a stale copy

When asked for an interview-prep walkthrough or project recap, generate it fresh from the current `LEDGER.md` at that time. Don't reuse or lightly edit a previous version — the ledger is the source of truth and it changes as milestones land. Per the user's instructions, don't produce this walkthrough at all until they explicitly ask for it.

## 6. After every future milestone

Append a new entry to `LEDGER.md` in the same format as the existing ones (status, merge date, commit/PR reference, what shipped, bugs found & fixed) — filled in only after independently verifying per Rule 2, not transcribed from a completion report.
