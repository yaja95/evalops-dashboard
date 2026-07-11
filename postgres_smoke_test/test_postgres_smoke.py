"""Live-Postgres smoke test — NOT part of the default `uv run pytest` suite.

Deliberately kept outside tests/ so tests/conftest.py's in-memory-SQLite
guard (EXPECTED_TEST_DATABASE_URL) never applies here. Run explicitly:

    EVALOPS_DATABASE_URL=postgresql+psycopg://... uv run pytest postgres_smoke_test/

CI's postgres-smoke job is the only place this normally runs, against a
real postgres: service container — see .github/workflows/ci.yml.
"""

import os

from sqlmodel import Session, select

EXPECTED_URL_PREFIX = "postgresql"

database_url = os.environ.get("EVALOPS_DATABASE_URL", "")
if not database_url.startswith(EXPECTED_URL_PREFIX):
    raise RuntimeError(
        "postgres_smoke_test requires EVALOPS_DATABASE_URL to point at a "
        f"Postgres database (postgresql://... or postgresql+psycopg://...); got {database_url!r}. "
        "This smoke test must not run against SQLite."
    )

from evalops_dashboard.auth import verify_password  # noqa: E402
from evalops_dashboard.database import engine  # noqa: E402
from evalops_dashboard.models import Evaluation, Prompt, User  # noqa: E402
from evalops_dashboard.seed import (  # noqa: E402
    SEED_USER_PASSWORD_FALLBACK,
    SEED_USERNAME,
    seed_database,
)


def test_seed_database_against_live_postgres() -> None:
    assert engine.dialect.name == "postgresql"

    with Session(engine) as session:
        seed_database(session)

        prompts = list(session.exec(select(Prompt)).all())
        assert len(prompts) >= 1

        evaluations = list(session.exec(select(Evaluation)).all())
        assert len(evaluations) >= 1
        for evaluation in evaluations:
            assert evaluation.response_id is not None
            assert evaluation.rubric_id is not None

        user = session.exec(select(User).where(User.username == SEED_USERNAME)).first()
        assert user is not None
        seed_password = os.environ.get("SEED_USER_PASSWORD", SEED_USER_PASSWORD_FALLBACK)
        assert verify_password(seed_password, user.password_hash)

        prompt_count_before = len(prompts)
        seed_database(session)
        prompts_after = list(session.exec(select(Prompt)).all())
        assert len(prompts_after) == prompt_count_before
