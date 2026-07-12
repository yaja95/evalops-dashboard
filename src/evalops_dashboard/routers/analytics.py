from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from evalops_dashboard.auth import CurrentUser
from evalops_dashboard.criteria_analytics import (
    CriterionScoreInput,
    build_criteria_analytics_summary,
)
from evalops_dashboard.database import get_session
from evalops_dashboard.models import (
    CriteriaAnalyticsRead,
    CriterionAnalyticsRead,
    CriterionScore,
    Evaluation,
    ModelCriterionAverageRead,
    ModelResponse,
    RubricCriterion,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/by-criterion", response_model=CriteriaAnalyticsRead)
def get_criteria_analytics(session: SessionDep, current_user: CurrentUser) -> CriteriaAnalyticsRead:
    rows = session.exec(
        select(CriterionScore.score, RubricCriterion.name, ModelResponse.model_name)
        .join(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .join(Evaluation, Evaluation.id == CriterionScore.evaluation_id)
        .join(ModelResponse, ModelResponse.id == Evaluation.response_id)
    ).all()

    summary = build_criteria_analytics_summary(
        [
            CriterionScoreInput(criterion_name=name, model_name=model_name, score=score)
            for score, name, model_name in rows
        ]
    )

    return CriteriaAnalyticsRead(
        criteria=[
            CriterionAnalyticsRead(
                criterion_name=criterion.criterion_name,
                evaluation_count=criterion.evaluation_count,
                average_score=criterion.average_score,
                models=[
                    ModelCriterionAverageRead(
                        model_name=model.model_name,
                        evaluation_count=model.evaluation_count,
                        average_score=model.average_score,
                    )
                    for model in criterion.models
                ],
            )
            for criterion in summary.criteria
        ]
    )
