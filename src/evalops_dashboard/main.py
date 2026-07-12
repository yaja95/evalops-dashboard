from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from evalops_dashboard.auth import CurrentUser, DashboardAuthRequired
from evalops_dashboard.cost import calculate_cost
from evalops_dashboard.database import engine, get_session
from evalops_dashboard.models import (
    AnalyticsSummary,
    Evaluation,
    ModelPricing,
    ModelResponse,
    ModelResponseCreate,
    Prompt,
    PromptCreate,
)
from evalops_dashboard.routers.auth import dashboard_auth_router, users_router
from evalops_dashboard.routers.auth import router as auth_router
from evalops_dashboard.routers.comparisons import router as comparisons_router
from evalops_dashboard.routers.dashboard import router as dashboard_router
from evalops_dashboard.routers.evaluations import router as evaluations_router
from evalops_dashboard.routers.pricing import router as pricing_router
from evalops_dashboard.routers.rubrics import router as rubrics_router
from evalops_dashboard.seed import seed_database

STATIC_DIR = Path(__file__).resolve().parent / "static"

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with Session(engine) as session:
        seed_database(session)
    yield


app = FastAPI(
    title="evalops-dashboard",
    summary="A lightweight AI evaluation operations API.",
    version="0.13.0",
    lifespan=lifespan,
)
app.include_router(evaluations_router)
app.include_router(rubrics_router)
app.include_router(comparisons_router)
app.include_router(dashboard_router)
app.include_router(pricing_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(dashboard_auth_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(DashboardAuthRequired)
def redirect_to_login(request: Request, exc: DashboardAuthRequired) -> RedirectResponse:
    return RedirectResponse(
        url=f"/login?next={exc.next_path}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "evalops-dashboard"}


@app.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics_summary(session: SessionDep, current_user: CurrentUser) -> AnalyticsSummary:
    prompts = list(session.exec(select(Prompt)).all())
    responses = list(session.exec(select(ModelResponse)).all())
    evaluations = list(session.exec(select(Evaluation)).all())

    return AnalyticsSummary(
        prompt_count=len(prompts),
        response_count=len(responses),
        evaluation_count=len(evaluations),
        average_overall_score=average_score(
            [evaluation.overall_score for evaluation in evaluations]
        ),
        pass_rate=calculate_pass_rate(evaluations),
    )


def average_score(scores: list[float]) -> float | None:
    if not scores:
        return None

    return round(sum(scores) / len(scores), 2)


def calculate_pass_rate(evaluations: list[Evaluation]) -> float:
    if not evaluations:
        return 0.0

    passing_evaluations = [evaluation for evaluation in evaluations if evaluation.passed]
    return round(len(passing_evaluations) / len(evaluations), 2)


@app.get("/prompts", response_model=list[Prompt])
def list_prompts(session: SessionDep, current_user: CurrentUser) -> list[Prompt]:
    return list(session.exec(select(Prompt)).all())


@app.post("/prompts", response_model=Prompt, status_code=status.HTTP_201_CREATED)
def create_prompt(
    prompt_create: PromptCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Prompt:
    prompt = Prompt.model_validate(prompt_create)
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt


@app.get("/responses", response_model=list[ModelResponse])
def list_model_responses(session: SessionDep, current_user: CurrentUser) -> list[ModelResponse]:
    return list(session.exec(select(ModelResponse)).all())


@app.post("/responses", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
def create_model_response(
    response_create: ModelResponseCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ModelResponse:
    prompt = session.get(Prompt, response_create.prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt {response_create.prompt_id} was not found.",
        )

    model_response = ModelResponse.model_validate(response_create)

    # Cost is server-calculated from a known pricing catalog, never client-submitted.
    # An unmatched provider/model or missing token counts just leaves cost_usd unset —
    # that's an expected, normal case, not an error.
    if response_create.input_tokens is not None and response_create.output_tokens is not None:
        pricing = session.exec(
            select(ModelPricing).where(
                ModelPricing.provider == response_create.provider,
                ModelPricing.model_name == response_create.model_name,
            )
        ).first()
        if pricing is not None:
            model_response.cost_usd = calculate_cost(
                input_tokens=response_create.input_tokens,
                output_tokens=response_create.output_tokens,
                input_price_per_1k_tokens=pricing.input_price_per_1k_tokens,
                output_price_per_1k_tokens=pricing.output_price_per_1k_tokens,
            )

    session.add(model_response)
    session.commit()
    session.refresh(model_response)
    return model_response
