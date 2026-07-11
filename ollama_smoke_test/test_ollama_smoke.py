"""Live-Ollama smoke test — NOT part of the default `uv run pytest` suite.

Deliberately kept outside tests/ so tests/conftest.py's guards (in-memory
SQLite, the get_current_user/get_judge_client dependency overrides) never
apply here. This test hits the real OllamaJudgeClient with no dependency
override, against a real Ollama server. Run explicitly:

    LLM_JUDGE_PROVIDER=ollama OLLAMA_HOST=http://127.0.0.1:11434 \
        uv run pytest ollama_smoke_test/ -v

CI's ollama-smoke job is the only place this normally runs, against a real
ollama/ollama service container — see .github/workflows/ci.yml.
"""

import os

EXPECTED_PROVIDER = "ollama"

provider = os.environ.get("LLM_JUDGE_PROVIDER", "").lower()
if provider != EXPECTED_PROVIDER:
    raise RuntimeError(
        f"ollama_smoke_test requires LLM_JUDGE_PROVIDER=ollama; got {provider!r}. "
        "This smoke test must not run against the default Anthropic-backed judge "
        "or a mocked client."
    )

from fastapi.testclient import TestClient  # noqa: E402

from evalops_dashboard.main import app  # noqa: E402
from evalops_dashboard.seed import SEED_USER_PASSWORD_FALLBACK, SEED_USERNAME  # noqa: E402


def test_auto_evaluation_against_live_ollama() -> None:
    with TestClient(app) as client:
        seed_password = os.environ.get("SEED_USER_PASSWORD", SEED_USER_PASSWORD_FALLBACK)
        login_response = client.post(
            "/auth/login",
            json={"username": SEED_USERNAME, "password": seed_password},
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]

        auto_evaluation_response = client.post(
            "/evaluations/auto",
            headers={"Authorization": f"Bearer {token}"},
            json={"response_id": 1, "rubric_id": 1},
        )

    assert auto_evaluation_response.status_code == 201
    body = auto_evaluation_response.json()
    assert body["evaluator"] == "ollama-judge"
    assert len(body["scores"]) >= 1
    for score in body["scores"]:
        assert 1 <= score["score"] <= 5
    assert body["justification"]
