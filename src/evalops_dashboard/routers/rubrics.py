from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from evalops_dashboard.auth import CurrentUser
from evalops_dashboard.database import get_session
from evalops_dashboard.models import (
    Rubric,
    RubricCreate,
    RubricCriterion,
    RubricCriterionRead,
    RubricRead,
)

router = APIRouter(prefix="/rubrics", tags=["rubrics"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=RubricRead, status_code=status.HTTP_201_CREATED)
def create_rubric(
    rubric_create: RubricCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> RubricRead:
    existing_rubric = session.exec(
        select(Rubric).where(
            Rubric.name == rubric_create.name,
            Rubric.version == rubric_create.version,
        )
    ).first()
    if existing_rubric is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rubric '{rubric_create.name}' version {rubric_create.version} already exists.",
        )

    rubric = Rubric.model_validate(rubric_create, update={"criteria": None})
    try:
        session.add(rubric)
        session.flush()

        criteria = [
            RubricCriterion.model_validate(
                criterion_create,
                update={"rubric_id": rubric.id},
            )
            for criterion_create in rubric_create.criteria
        ]
        session.add_all(criteria)
        session.commit()
        session.refresh(rubric)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rubric or criterion uniqueness constraint was violated.",
        ) from exc

    return build_rubric_response(rubric, session)


@router.get("", response_model=list[RubricRead])
def list_rubrics(session: SessionDep, current_user: CurrentUser) -> list[RubricRead]:
    rubrics = session.exec(select(Rubric).order_by(Rubric.name, Rubric.version, Rubric.id)).all()
    return [build_rubric_response(rubric, session) for rubric in rubrics]


@router.get("/{rubric_id}", response_model=RubricRead)
def get_rubric(rubric_id: int, session: SessionDep, current_user: CurrentUser) -> RubricRead:
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} was not found.",
        )

    return build_rubric_response(rubric, session)


def build_rubric_response(rubric: Rubric, session: Session) -> RubricRead:
    criteria = session.exec(
        select(RubricCriterion)
        .where(RubricCriterion.rubric_id == rubric.id)
        .order_by(RubricCriterion.id)
    ).all()
    return RubricRead(
        id=rubric.id or 0,
        name=rubric.name,
        version=rubric.version,
        description=rubric.description,
        pass_threshold=rubric.pass_threshold,
        created_at=rubric.created_at,
        criteria=[
            RubricCriterionRead(
                id=criterion.id or 0,
                rubric_id=criterion.rubric_id,
                name=criterion.name,
                description=criterion.description,
                weight=criterion.weight,
                min_score=criterion.min_score,
                max_score=criterion.max_score,
                required=criterion.required,
            )
            for criterion in criteria
        ],
    )
