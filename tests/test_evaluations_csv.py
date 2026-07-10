import csv
import io

from fastapi.testclient import TestClient

from evalops_dashboard.main import app

NONEXISTENT_ID = 999999


def test_export_returns_csv_matching_created_evaluations() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Export Rubric")
        response_one = create_response(client, "Export Prompt One")
        response_two = create_response(client, "Export Prompt Two")
        create_evaluation(client, response_one, rubric, scores=[5, 4])
        create_evaluation(client, response_two, rubric, scores=[3, 5])

        response = client.get(f"/evaluations/export?rubric_id={rubric['id']}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert rows[0]["response_id"] == str(response_one)
    assert rows[0]["Instruction Following_score"] == "5"
    assert rows[0]["Accuracy_score"] == "4"
    assert rows[1]["response_id"] == str(response_two)
    assert rows[1]["Instruction Following_score"] == "3"
    assert rows[1]["Accuracy_score"] == "5"


def test_reimporting_exported_csv_creates_new_evaluations_without_dedup() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Reimport Rubric")
        response_id = create_response(client, "Reimport Prompt")
        create_evaluation(client, response_id, rubric, scores=[5, 4])

        exported = client.get(f"/evaluations/export?rubric_id={rubric['id']}")
        assert exported.status_code == 200

        import_response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", exported.content, "text/csv")},
        )
        assert import_response.status_code == 200
        assert import_response.json() == {"created_count": 1, "errors": []}

        evaluations = client.get("/evaluations").json()

    matching = [e for e in evaluations if e["rubric_id"] == rubric["id"]]
    assert len(matching) == 2


def test_partial_success_reports_row_errors_and_creates_valid_rows() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Partial Rubric")
        response_one = create_response(client, "Partial Prompt One")
        response_two = create_response(client, "Partial Prompt Two")
        response_three = create_response(client, "Partial Prompt Three")

        csv_bytes = build_csv(
            rubric,
            [
                (response_one, "eval-a", "row one good", [5, 4]),
                (response_two, "eval-b", "row two bad score", ["oops", 4]),
                (response_three, "eval-c", "row three good", [3, 5]),
            ],
        )
        import_response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", csv_bytes, "text/csv")},
        )

        evaluations = client.get("/evaluations").json()

    assert import_response.status_code == 200
    body = import_response.json()
    assert body["created_count"] == 2
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 2

    matching = [e for e in evaluations if e["rubric_id"] == rubric["id"]]
    assert len(matching) == 2


def test_export_404_for_missing_rubric() -> None:
    with TestClient(app) as client:
        response = client.get(f"/evaluations/export?rubric_id={NONEXISTENT_ID}")

    assert response.status_code == 404


def test_import_404_for_missing_rubric() -> None:
    with TestClient(app) as client:
        response = client.post(
            f"/evaluations/import?rubric_id={NONEXISTENT_ID}",
            files={"file": ("evaluations.csv", b"response_id\n1\n", "text/csv")},
        )

    assert response.status_code == 404


def test_export_returns_header_only_csv_for_rubric_with_no_evaluations() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Empty Rubric")
        response = client.get(f"/evaluations/export?rubric_id={rubric['id']}")

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows == []


def test_import_rejects_csv_missing_a_column() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Missing Column Rubric")
        columns = [column for column in build_columns(rubric) if column != "Accuracy_notes"]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns)
        writer.writerow([1, "eval", "text", 5, "", 4])

        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", buffer.getvalue().encode(), "text/csv")},
        )

    assert response.status_code == 422
    assert "Accuracy_notes" in response.json()["detail"]


def test_import_rejects_csv_with_unexpected_column() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Unexpected Column Rubric")
        columns = [*build_columns(rubric), "extra_column"]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns)
        writer.writerow([1, "eval", "text", 5, "", 4, "", "surprise"])

        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", buffer.getvalue().encode(), "text/csv")},
        )

    assert response.status_code == 422
    assert "extra_column" in response.json()["detail"]


def test_import_reports_row_error_for_non_integer_score() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Bad Score Rubric")
        response_id = create_response(client, "Bad Score Prompt")
        csv_bytes = build_csv(
            rubric,
            [(response_id, "eval", "text", ["not-a-number", 4])],
        )

        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", csv_bytes, "text/csv")},
        )

    body = response.json()
    assert body["created_count"] == 0
    assert "Instruction Following" in body["errors"][0]["detail"]


def test_import_row_error_matches_json_api_validation_message() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Out Of Bounds Rubric")
        response_id = create_response(client, "Out Of Bounds Prompt")
        csv_bytes = build_csv(
            rubric,
            [(response_id, "eval", "text", [9, 4])],
        )

        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", csv_bytes, "text/csv")},
        )

    body = response.json()
    assert body["created_count"] == 0
    assert "must be no greater than" in body["errors"][0]["detail"]


def test_import_rejects_empty_file() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Empty File Rubric")
        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", b"", "text/csv")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "CSV file is empty."


def test_import_accepts_header_only_csv_with_zero_created() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Header Only Rubric")
        buffer = io.StringIO()
        csv.writer(buffer).writerow(build_columns(rubric))

        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", buffer.getvalue().encode(), "text/csv")},
        )

    assert response.status_code == 200
    assert response.json() == {"created_count": 0, "errors": []}


def test_import_reports_row_error_for_blank_evaluator() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Blank Evaluator Rubric")
        response_one = create_response(client, "Blank Evaluator Prompt One")
        response_two = create_response(client, "Blank Evaluator Prompt Two")
        csv_bytes = build_csv(
            rubric,
            [
                (response_one, "", "text", [5, 4]),
                (response_two, "eval", "text", [4, 5]),
            ],
        )

        response = client.post(
            f"/evaluations/import?rubric_id={rubric['id']}",
            files={"file": ("evaluations.csv", csv_bytes, "text/csv")},
        )

    body = response.json()
    assert body["created_count"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 1


def create_response(client: TestClient, title: str) -> int:
    prompt_response = client.post(
        "/prompts",
        json={
            "title": title,
            "content": "Evaluate this model response.",
            "use_case": "evaluation",
            "owner": "tests",
        },
    )
    prompt_id = prompt_response.json()["id"]
    model_response = client.post(
        "/responses",
        json={
            "prompt_id": prompt_id,
            "model_name": "gpt-example-test",
            "response_text": "This is the model response to evaluate.",
            "latency_ms": 100,
        },
    )
    return model_response.json()["id"]


def create_rubric(client: TestClient, name: str) -> dict:
    response = client.post(
        "/rubrics",
        json={
            "name": name,
            "version": 1,
            "description": "CSV test rubric.",
            "pass_threshold": 4,
            "criteria": [
                criterion_payload("Instruction Following", weight=2, required=True),
                criterion_payload("Accuracy", weight=1, required=True),
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def criterion_payload(name: str, weight: float, required: bool) -> dict:
    return {
        "name": name,
        "description": f"{name} criterion.",
        "weight": weight,
        "min_score": 1,
        "max_score": 5,
        "required": required,
    }


def create_evaluation(
    client: TestClient,
    response_id: int,
    rubric: dict,
    scores: list[int],
    evaluator: str = "ajay",
) -> dict:
    response = client.post(
        "/evaluations",
        json={
            "response_id": response_id,
            "rubric_id": rubric["id"],
            "justification": "CSV test evaluation.",
            "evaluator": evaluator,
            "scores": [
                {
                    "criterion_id": criterion["id"],
                    "score": scores[index],
                    "notes": "",
                }
                for index, criterion in enumerate(rubric["criteria"])
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def build_columns(rubric: dict) -> list[str]:
    columns = ["response_id", "evaluator", "justification"]
    for criterion in rubric["criteria"]:
        columns.append(f"{criterion['name']}_score")
        columns.append(f"{criterion['name']}_notes")
    return columns


def build_csv(rubric: dict, rows: list[tuple]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(build_columns(rubric))
    for response_id, evaluator, justification, scores in rows:
        row = [response_id, evaluator, justification]
        for score in scores:
            row.append(score)
            row.append("")
        writer.writerow(row)
    return buffer.getvalue().encode()
