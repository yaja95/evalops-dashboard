import os

os.environ["EVALOPS_DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient

from evalops_dashboard.main import app


def rubric_payload(name: str = "Support Response Quality", version: int = 1) -> dict:
    return {
        "name": name,
        "version": version,
        "description": "Evaluates customer-support responses.",
        "pass_threshold": 4,
        "criteria": [
            {
                "name": "Instruction Following",
                "description": "The response addresses the requested task.",
                "weight": 2,
                "min_score": 1,
                "max_score": 5,
                "required": True,
            },
            {
                "name": "Clarity",
                "description": "The response is clear and understandable.",
                "weight": 1,
                "min_score": 1,
                "max_score": 5,
                "required": True,
            },
        ],
    }


def test_create_rubric_with_multiple_criteria() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/rubrics",
            json=rubric_payload("Support Response Quality Create", 1),
        )

    assert response.status_code == 201
    response_body = response.json()
    assert response_body["name"] == "Support Response Quality Create"
    assert response_body["version"] == 1
    assert response_body["pass_threshold"] == 4
    assert len(response_body["criteria"]) == 2
    assert response_body["criteria"][0]["name"] == "Instruction Following"
    assert response_body["criteria"][0]["rubric_id"] == response_body["id"]


def test_list_rubrics_with_nested_criteria() -> None:
    with TestClient(app) as client:
        client.post("/rubrics", json=rubric_payload("A Listed Rubric", 1))
        client.post("/rubrics", json=rubric_payload("Z Listed Rubric", 1))

        response = client.get("/rubrics")

    assert response.status_code == 200
    rubrics = response.json()
    rubric_names = [rubric["name"] for rubric in rubrics]
    assert rubric_names == sorted(rubric_names)
    listed_rubric = next(rubric for rubric in rubrics if rubric["name"] == "A Listed Rubric")
    assert len(listed_rubric["criteria"]) == 2
    assert listed_rubric["criteria"][1]["name"] == "Clarity"


def test_get_one_rubric() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/rubrics",
            json=rubric_payload("Single Rubric Lookup", 1),
        )
        rubric_id = create_response.json()["id"]

        response = client.get(f"/rubrics/{rubric_id}")

    assert response.status_code == 200
    assert response.json()["id"] == rubric_id
    assert response.json()["name"] == "Single Rubric Lookup"
    assert len(response.json()["criteria"]) == 2


def test_get_nonexistent_rubric_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/rubrics/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Rubric 999999 was not found."


def test_rejects_rubric_with_no_criteria() -> None:
    payload = rubric_payload("No Criteria Rubric", 1)
    payload["criteria"] = []

    with TestClient(app) as client:
        response = client.post("/rubrics", json=payload)

    assert response.status_code == 422


def test_rejects_duplicate_criterion_names_case_insensitively() -> None:
    payload = rubric_payload("Duplicate Criterion Rubric", 1)
    payload["criteria"][1]["name"] = "instruction following"

    with TestClient(app) as client:
        response = client.post("/rubrics", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("weight", 0),
        ("min_score", 0),
        ("max_score", 6),
    ],
)
def test_rejects_invalid_criterion_bounds(field_name: str, value: int) -> None:
    payload = rubric_payload(f"Invalid {field_name} Rubric", 1)
    payload["criteria"][0][field_name] = value

    with TestClient(app) as client:
        response = client.post("/rubrics", json=payload)

    assert response.status_code == 422


def test_rejects_invalid_score_range() -> None:
    payload = rubric_payload("Invalid Range Rubric", 1)
    payload["criteria"][0]["min_score"] = 5
    payload["criteria"][0]["max_score"] = 5

    with TestClient(app) as client:
        response = client.post("/rubrics", json=payload)

    assert response.status_code == 422


def test_rejects_duplicate_rubric_name_and_version() -> None:
    payload = rubric_payload("Duplicate Rubric Version", 1)

    with TestClient(app) as client:
        first_response = client.post("/rubrics", json=payload)
        second_response = client.post("/rubrics", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert (
        second_response.json()["detail"]
        == "Rubric 'Duplicate Rubric Version' version 1 already exists."
    )
