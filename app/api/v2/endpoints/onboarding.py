import uuid

from fastapi import APIRouter, Depends, Request

from app.api.v2.deps import get_current_user_id
from app.core.limiter import limiter
from app.schemas.v2.library import OnboardingIn
from app.schemas.v2.user import UserMe
from app.services import user_service

router = APIRouter()


@router.put("", response_model=UserMe)
@limiter.limit("10/minute")
def complete_onboarding(request: Request, data: OnboardingIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    return user_service.complete_onboarding(user_id, data)
