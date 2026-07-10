from fastapi.testclient import TestClient

from evalops_dashboard.main import app

NONEXISTENT_ID = 999999


def pricing_payload(
    provider: str = "openai-example",
    model_name: str = "test-model",
) -> dict:
    return {
        "provider": provider,
        "model_name": model_name,
        "input_price_per_1k_tokens": 0.01,
        "output_price_per_1k_tokens": 0.03,
    }


def test_create_model_pricing() -> None:
    with TestClient(app) as client:
        response = client.post("/model-pricing", json=pricing_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "openai-example"
    assert body["model_name"] == "test-model"
    assert body["input_price_per_1k_tokens"] == 0.01
    assert body["output_price_per_1k_tokens"] == 0.03
    assert "id" in body
    assert "created_at" in body


def test_rejects_duplicate_provider_and_model_name() -> None:
    with TestClient(app) as client:
        first = client.post("/model-pricing", json=pricing_payload())
        assert first.status_code == 201

        second = client.post("/model-pricing", json=pricing_payload())

    assert second.status_code == 409


def test_list_model_pricing_includes_created_entries() -> None:
    with TestClient(app) as client:
        client.post("/model-pricing", json=pricing_payload(model_name="model-a"))
        client.post("/model-pricing", json=pricing_payload(model_name="model-b"))

        response = client.get("/model-pricing")

    assert response.status_code == 200
    model_names = {entry["model_name"] for entry in response.json()}
    assert {"model-a", "model-b"}.issubset(model_names)


def test_get_model_pricing_detail() -> None:
    with TestClient(app) as client:
        created = client.post("/model-pricing", json=pricing_payload()).json()

        response = client.get(f"/model-pricing/{created['id']}")

    assert response.status_code == 200
    assert response.json()["model_name"] == "test-model"


def test_get_nonexistent_model_pricing_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get(f"/model-pricing/{NONEXISTENT_ID}")

    assert response.status_code == 404
