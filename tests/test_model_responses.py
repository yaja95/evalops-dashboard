from fastapi.testclient import TestClient

from evalops_dashboard.main import app


def create_prompt(client: TestClient, title: str = "Cost Test Prompt") -> int:
    response = client.post(
        "/prompts",
        json={
            "title": title,
            "content": "Evaluate this model response.",
            "use_case": "cost tracking",
            "owner": "tests",
        },
    )
    return response.json()["id"]


def test_create_and_list_model_responses() -> None:
    with TestClient(app) as client:
        prompt_id = create_prompt(client)
        create_response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "plain-model",
                "response_text": "A response.",
                "latency_ms": 100,
            },
        )
        list_response = client.get("/responses")

    assert create_response.status_code == 201
    assert any(r["model_name"] == "plain-model" for r in list_response.json())


def test_cost_calculated_when_tokens_and_pricing_match() -> None:
    with TestClient(app) as client:
        prompt_id = create_prompt(client)
        client.post(
            "/model-pricing",
            json={
                "provider": "test-provider",
                "model_name": "priced-model",
                "input_price_per_1k_tokens": 0.01,
                "output_price_per_1k_tokens": 0.03,
            },
        )

        response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "priced-model",
                "response_text": "A response.",
                "provider": "test-provider",
                "input_tokens": 1000,
                "output_tokens": 500,
            },
        )

    assert response.status_code == 201
    # (1000/1000)*0.01 + (500/1000)*0.03 = 0.01 + 0.015 = 0.025
    assert response.json()["cost_usd"] == 0.025


def test_cost_is_none_when_no_matching_pricing() -> None:
    with TestClient(app) as client:
        prompt_id = create_prompt(client)

        response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "unpriced-model",
                "response_text": "A response.",
                "provider": "unknown-provider",
                "input_tokens": 1000,
                "output_tokens": 500,
            },
        )

    assert response.status_code == 201
    assert response.json()["cost_usd"] is None


def test_cost_is_none_when_tokens_not_provided() -> None:
    with TestClient(app) as client:
        prompt_id = create_prompt(client)
        client.post(
            "/model-pricing",
            json={
                "provider": "test-provider",
                "model_name": "priced-model-no-tokens",
                "input_price_per_1k_tokens": 0.01,
                "output_price_per_1k_tokens": 0.03,
            },
        )

        response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "priced-model-no-tokens",
                "response_text": "A response.",
                "provider": "test-provider",
            },
        )

    assert response.status_code == 201
    assert response.json()["cost_usd"] is None


def test_rejects_client_submitted_cost() -> None:
    with TestClient(app) as client:
        prompt_id = create_prompt(client)

        response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "sneaky-model",
                "response_text": "A response.",
                "cost_usd": 999.99,
            },
        )

    assert response.status_code == 422
