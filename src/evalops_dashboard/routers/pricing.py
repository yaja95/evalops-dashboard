from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from evalops_dashboard.auth import CurrentUser
from evalops_dashboard.database import get_session
from evalops_dashboard.models import ModelPricing, ModelPricingCreate, ModelPricingRead

router = APIRouter(prefix="/model-pricing", tags=["pricing"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=ModelPricingRead, status_code=status.HTTP_201_CREATED)
def create_model_pricing(
    pricing_create: ModelPricingCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ModelPricingRead:
    existing_pricing = session.exec(
        select(ModelPricing).where(
            ModelPricing.provider == pricing_create.provider,
            ModelPricing.model_name == pricing_create.model_name,
        )
    ).first()
    if existing_pricing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pricing for provider '{pricing_create.provider}' model "
                f"'{pricing_create.model_name}' already exists."
            ),
        )

    pricing = ModelPricing.model_validate(pricing_create)
    try:
        session.add(pricing)
        session.commit()
        session.refresh(pricing)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model pricing uniqueness constraint was violated.",
        ) from exc

    return pricing


@router.get("", response_model=list[ModelPricingRead])
def list_model_pricing(session: SessionDep, current_user: CurrentUser) -> list[ModelPricing]:
    return list(
        session.exec(
            select(ModelPricing).order_by(ModelPricing.provider, ModelPricing.model_name)
        ).all()
    )


@router.get("/{pricing_id}", response_model=ModelPricingRead)
def get_model_pricing(
    pricing_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> ModelPricing:
    pricing = session.get(ModelPricing, pricing_id)
    if pricing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model pricing {pricing_id} was not found.",
        )

    return pricing
