from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from evalops_dashboard.auth import CurrentDashboardUser
from evalops_dashboard.database import get_session
from evalops_dashboard.models import Evaluation, ModelResponse, Prompt, PromptComparisonRead, Rubric
from evalops_dashboard.routers.analytics import get_criteria_analytics
from evalops_dashboard.routers.comparisons import compare_prompt_responses
from evalops_dashboard.routers.evaluations import build_evaluation_responses
from evalops_dashboard.routers.rubrics import build_rubric_response

MAX_SCORE = 5.0

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("")
def dashboard_index(request: Request, session: SessionDep, current_user: CurrentDashboardUser):
    counts = {
        "prompts": len(session.exec(select(Prompt)).all()),
        "responses": len(session.exec(select(ModelResponse)).all()),
        "rubrics": len(session.exec(select(Rubric)).all()),
        "evaluations": len(session.exec(select(Evaluation)).all()),
    }
    return templates.TemplateResponse(
        request, "index.html", {"counts": counts, "current_user": current_user}
    )


@router.get("/analytics")
def criteria_analytics_page(
    request: Request, session: SessionDep, current_user: CurrentDashboardUser
):
    analytics = get_criteria_analytics(session, current_user)
    charts = [
        CriterionChart(
            title=criterion.criterion_name,
            rows=[
                BarChartRow(
                    label=model.model_name,
                    display_value=f"{model.average_score:.2f}",
                    percent=_percent(model.average_score, MAX_SCORE),
                )
                for model in criterion.models
            ],
        )
        for criterion in analytics.criteria
    ]
    return templates.TemplateResponse(
        request, "analytics.html", {"charts": charts, "current_user": current_user}
    )


@router.get("/prompts")
def list_prompts_page(request: Request, session: SessionDep, current_user: CurrentDashboardUser):
    prompts = list(session.exec(select(Prompt).order_by(Prompt.id)).all())
    return templates.TemplateResponse(
        request,
        "prompts_list.html",
        {"prompts": prompts, "current_user": current_user},
    )


@router.get("/prompts/{prompt_id}")
def prompt_detail_page(
    prompt_id: int,
    request: Request,
    session: SessionDep,
    current_user: CurrentDashboardUser,
):
    prompt = session.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt {prompt_id} was not found.",
        )

    responses = list(
        session.exec(
            select(ModelResponse)
            .where(ModelResponse.prompt_id == prompt_id)
            .order_by(ModelResponse.id)
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "prompt_detail.html",
        {"prompt": prompt, "responses": responses, "current_user": current_user},
    )


@router.get("/prompts/{prompt_id}/comparison")
def prompt_comparison_page(
    prompt_id: int,
    request: Request,
    session: SessionDep,
    current_user: CurrentDashboardUser,
    rubric_id: int | None = None,
):
    prompt = session.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt {prompt_id} was not found.",
        )

    applicable_rubrics = build_applicable_rubrics(prompt_id, session)
    applicable_rubric_ids = {rubric.id for rubric in applicable_rubrics}

    if rubric_id is None:
        if len(applicable_rubrics) == 1:
            rubric_id = applicable_rubrics[0].id
        else:
            return templates.TemplateResponse(
                request,
                "prompt_comparison.html",
                {
                    "prompt": prompt,
                    "applicable_rubrics": applicable_rubrics,
                    "selected_rubric_id": None,
                    "comparison": None,
                    "chart_data": None,
                    "current_user": current_user,
                },
            )
    elif rubric_id not in applicable_rubric_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} has not evaluated any responses for prompt {prompt_id}.",
        )

    comparison = compare_prompt_responses(prompt_id, rubric_id, session, current_user)
    chart_data = build_chart_rows(comparison) if comparison.comparison_ready else None

    return templates.TemplateResponse(
        request,
        "prompt_comparison.html",
        {
            "prompt": prompt,
            "applicable_rubrics": applicable_rubrics,
            "selected_rubric_id": rubric_id,
            "comparison": comparison,
            "chart_data": chart_data,
            "current_user": current_user,
        },
    )


@router.get("/responses")
def list_responses_page(request: Request, session: SessionDep, current_user: CurrentDashboardUser):
    responses = list(session.exec(select(ModelResponse).order_by(ModelResponse.id)).all())
    prompts_by_id = build_prompts_by_id(responses, session)
    return templates.TemplateResponse(
        request,
        "responses_list.html",
        {"responses": responses, "prompts_by_id": prompts_by_id, "current_user": current_user},
    )


@router.get("/responses/{response_id}")
def response_detail_page(
    response_id: int,
    request: Request,
    session: SessionDep,
    current_user: CurrentDashboardUser,
):
    model_response = session.get(ModelResponse, response_id)
    if model_response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model response {response_id} was not found.",
        )

    evaluations = list(
        session.exec(
            select(Evaluation).where(Evaluation.response_id == response_id).order_by(Evaluation.id)
        ).all()
    )
    evaluation_reads = build_evaluation_responses(evaluations, session)
    return templates.TemplateResponse(
        request,
        "response_detail.html",
        {"response": model_response, "evaluations": evaluation_reads, "current_user": current_user},
    )


@router.get("/rubrics")
def list_rubrics_page(request: Request, session: SessionDep, current_user: CurrentDashboardUser):
    rubrics = list(session.exec(select(Rubric).order_by(Rubric.name, Rubric.version)).all())
    rubric_reads = [build_rubric_response(rubric, session) for rubric in rubrics]
    return templates.TemplateResponse(
        request,
        "rubrics_list.html",
        {"rubrics": rubric_reads, "current_user": current_user},
    )


@router.get("/rubrics/{rubric_id}")
def rubric_detail_page(
    rubric_id: int,
    request: Request,
    session: SessionDep,
    current_user: CurrentDashboardUser,
):
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} was not found.",
        )

    rubric_read = build_rubric_response(rubric, session)
    return templates.TemplateResponse(
        request,
        "rubric_detail.html",
        {"rubric": rubric_read, "current_user": current_user},
    )


@router.get("/evaluations")
def list_evaluations_page(
    request: Request, session: SessionDep, current_user: CurrentDashboardUser
):
    evaluations = list(session.exec(select(Evaluation).order_by(Evaluation.id)).all())
    evaluation_reads = build_evaluation_responses(evaluations, session)
    return templates.TemplateResponse(
        request,
        "evaluations_list.html",
        {"evaluations": evaluation_reads, "current_user": current_user},
    )


@router.get("/evaluations/{evaluation_id}")
def evaluation_detail_page(
    evaluation_id: int,
    request: Request,
    session: SessionDep,
    current_user: CurrentDashboardUser,
):
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} was not found.",
        )

    evaluation_read = build_evaluation_responses([evaluation], session)[0]
    return templates.TemplateResponse(
        request,
        "evaluation_detail.html",
        {"evaluation": evaluation_read, "current_user": current_user},
    )


def build_prompts_by_id(
    responses: list[ModelResponse],
    session: Session,
) -> dict[int, Prompt]:
    prompt_ids = {response.prompt_id for response in responses}
    if not prompt_ids:
        return {}

    prompts = session.exec(select(Prompt).where(Prompt.id.in_(prompt_ids))).all()
    return {prompt.id: prompt for prompt in prompts if prompt.id is not None}


def build_applicable_rubrics(prompt_id: int, session: Session) -> list[Rubric]:
    return list(
        session.exec(
            select(Rubric)
            .join(Evaluation, Evaluation.rubric_id == Rubric.id)
            .join(ModelResponse, ModelResponse.id == Evaluation.response_id)
            .where(ModelResponse.prompt_id == prompt_id)
            .distinct()
            .order_by(Rubric.name, Rubric.version)
        ).all()
    )


@dataclass(frozen=True)
class BarChartRow:
    label: str
    display_value: str
    percent: float
    is_winner: bool = False


@dataclass(frozen=True)
class CriterionChart:
    title: str
    rows: list[BarChartRow]


@dataclass(frozen=True)
class ChartData:
    quality: list[BarChartRow]
    pass_rate: list[BarChartRow]
    latency: list[BarChartRow]
    criteria: list[CriterionChart]


def build_chart_rows(comparison: PromptComparisonRead) -> ChartData:
    results = comparison.results
    winner_id = comparison.winner_response_id

    quality = [
        BarChartRow(
            label=result.model_name,
            display_value=f"{result.average_overall_score:.2f}",
            percent=_percent(result.average_overall_score, MAX_SCORE),
            is_winner=result.response_id == winner_id,
        )
        for result in results
    ]

    pass_rate = [
        BarChartRow(
            label=result.model_name,
            display_value=f"{result.pass_rate * 100:.0f}%",
            percent=_percent(result.pass_rate, 1.0),
            is_winner=result.response_id == winner_id,
        )
        for result in results
    ]

    max_latency = max(
        (result.latency_ms for result in results if result.latency_ms is not None),
        default=0,
    )
    latency = [
        BarChartRow(
            label=result.model_name,
            display_value=f"{result.latency_ms} ms" if result.latency_ms is not None else "—",
            percent=(
                _percent(result.latency_ms, max_latency) if result.latency_ms is not None else 0.0
            ),
            is_winner=result.response_id == winner_id,
        )
        for result in results
    ]

    criteria_by_name: dict[str, list[BarChartRow]] = {}
    for result in results:
        for criterion_average in result.criterion_averages:
            criteria_by_name.setdefault(criterion_average.criterion_name, []).append(
                BarChartRow(
                    label=result.model_name,
                    display_value=f"{criterion_average.average_score:.2f}",
                    percent=_percent(criterion_average.average_score, MAX_SCORE),
                )
            )
    criteria = [CriterionChart(title=name, rows=rows) for name, rows in criteria_by_name.items()]

    return ChartData(quality=quality, pass_rate=pass_rate, latency=latency, criteria=criteria)


def _percent(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return round(min(100.0, max(0.0, (value / max_value) * 100)), 2)
