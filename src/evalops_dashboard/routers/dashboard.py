from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from evalops_dashboard.database import get_session
from evalops_dashboard.models import Evaluation, ModelResponse, Prompt, Rubric
from evalops_dashboard.routers.evaluations import build_evaluation_responses
from evalops_dashboard.routers.rubrics import build_rubric_response

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("")
def dashboard_index(request: Request, session: SessionDep):
    counts = {
        "prompts": len(session.exec(select(Prompt)).all()),
        "responses": len(session.exec(select(ModelResponse)).all()),
        "rubrics": len(session.exec(select(Rubric)).all()),
        "evaluations": len(session.exec(select(Evaluation)).all()),
    }
    return templates.TemplateResponse(request, "index.html", {"counts": counts})


@router.get("/prompts")
def list_prompts_page(request: Request, session: SessionDep):
    prompts = list(session.exec(select(Prompt).order_by(Prompt.id)).all())
    return templates.TemplateResponse(request, "prompts_list.html", {"prompts": prompts})


@router.get("/prompts/{prompt_id}")
def prompt_detail_page(prompt_id: int, request: Request, session: SessionDep):
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
        {"prompt": prompt, "responses": responses},
    )


@router.get("/responses")
def list_responses_page(request: Request, session: SessionDep):
    responses = list(session.exec(select(ModelResponse).order_by(ModelResponse.id)).all())
    prompts_by_id = build_prompts_by_id(responses, session)
    return templates.TemplateResponse(
        request,
        "responses_list.html",
        {"responses": responses, "prompts_by_id": prompts_by_id},
    )


@router.get("/responses/{response_id}")
def response_detail_page(response_id: int, request: Request, session: SessionDep):
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
        {"response": model_response, "evaluations": evaluation_reads},
    )


@router.get("/rubrics")
def list_rubrics_page(request: Request, session: SessionDep):
    rubrics = list(session.exec(select(Rubric).order_by(Rubric.name, Rubric.version)).all())
    rubric_reads = [build_rubric_response(rubric, session) for rubric in rubrics]
    return templates.TemplateResponse(request, "rubrics_list.html", {"rubrics": rubric_reads})


@router.get("/rubrics/{rubric_id}")
def rubric_detail_page(rubric_id: int, request: Request, session: SessionDep):
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} was not found.",
        )

    rubric_read = build_rubric_response(rubric, session)
    return templates.TemplateResponse(request, "rubric_detail.html", {"rubric": rubric_read})


@router.get("/evaluations")
def list_evaluations_page(request: Request, session: SessionDep):
    evaluations = list(session.exec(select(Evaluation).order_by(Evaluation.id)).all())
    evaluation_reads = build_evaluation_responses(evaluations, session)
    return templates.TemplateResponse(
        request, "evaluations_list.html", {"evaluations": evaluation_reads}
    )


@router.get("/evaluations/{evaluation_id}")
def evaluation_detail_page(evaluation_id: int, request: Request, session: SessionDep):
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} was not found.",
        )

    evaluation_read = build_evaluation_responses([evaluation], session)[0]
    return templates.TemplateResponse(
        request, "evaluation_detail.html", {"evaluation": evaluation_read}
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
