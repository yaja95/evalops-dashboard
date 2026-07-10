from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlmodel import Session, select

from evalops_dashboard.database import engine, get_session
from evalops_dashboard.models import (
    AnalyticsSummary,
    Evaluation,
    EvaluationCreate,
    ModelResponse,
    ModelResponseCreate,
    Prompt,
    PromptCreate,
)
from evalops_dashboard.routers.rubrics import router as rubrics_router
from evalops_dashboard.seed import seed_database

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with Session(engine) as session:
        seed_database(session)
    yield


app = FastAPI(
    title="evalops-dashboard",
    summary="A lightweight AI evaluation operations API.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(rubrics_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "evalops-dashboard"}


@app.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics_summary(session: SessionDep) -> AnalyticsSummary:
    prompts = list(session.exec(select(Prompt)).all())
    responses = list(session.exec(select(ModelResponse)).all())
    evaluations = list(session.exec(select(Evaluation)).all())

    evaluation_count = len(evaluations)
    failure_categories = [
        evaluation.failure_category
        for evaluation in evaluations
        if evaluation.failure_category is not None
    ]

    return AnalyticsSummary(
        prompt_count=len(prompts),
        response_count=len(responses),
        evaluation_count=evaluation_count,
        average_overall_score=average_score(
            [evaluation.overall_score for evaluation in evaluations]
        ),
        average_truthfulness_score=average_score(
            [evaluation.truthfulness_score for evaluation in evaluations]
        ),
        most_common_failure_category=most_common_value(failure_categories),
        pass_rate=calculate_pass_rate(evaluations),
    )


def average_score(scores: list[int]) -> float | None:
    if not scores:
        return None

    return round(sum(scores) / len(scores), 2)


def most_common_value(values: list[str]) -> str | None:
    if not values:
        return None

    return Counter(values).most_common(1)[0][0]


def calculate_pass_rate(evaluations: list[Evaluation]) -> float:
    if not evaluations:
        return 0.0

    passing_evaluations = [
        evaluation for evaluation in evaluations if evaluation.overall_score >= 4
    ]
    return round(len(passing_evaluations) / len(evaluations), 2)


@app.get("/prompts", response_model=list[Prompt])
def list_prompts(session: SessionDep) -> list[Prompt]:
    return list(session.exec(select(Prompt)).all())


@app.post("/prompts", response_model=Prompt, status_code=status.HTTP_201_CREATED)
def create_prompt(prompt_create: PromptCreate, session: SessionDep) -> Prompt:
    prompt = Prompt.model_validate(prompt_create)
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt


@app.get("/responses", response_model=list[ModelResponse])
def list_model_responses(session: SessionDep) -> list[ModelResponse]:
    return list(session.exec(select(ModelResponse)).all())


@app.post("/responses", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
def create_model_response(
    response_create: ModelResponseCreate,
    session: SessionDep,
) -> ModelResponse:
    prompt = session.get(Prompt, response_create.prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt {response_create.prompt_id} was not found.",
        )

    model_response = ModelResponse.model_validate(response_create)
    session.add(model_response)
    session.commit()
    session.refresh(model_response)
    return model_response


@app.get("/evaluations", response_model=list[Evaluation])
def list_evaluations(session: SessionDep) -> list[Evaluation]:
    return list(session.exec(select(Evaluation)).all())


@app.post("/evaluations", response_model=Evaluation, status_code=status.HTTP_201_CREATED)
def create_evaluation(
    evaluation_create: EvaluationCreate,
    session: SessionDep,
) -> Evaluation:
    model_response = session.get(ModelResponse, evaluation_create.response_id)
    if model_response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model response {evaluation_create.response_id} was not found.",
        )

    evaluation = Evaluation.model_validate(evaluation_create)
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    return evaluation
