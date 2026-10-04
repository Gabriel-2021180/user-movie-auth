import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.api.v2.deps import get_current_user_id
from app.core.limiter import limiter
from app.schemas.v2.recommendation import DismissIn, RecommendationPage
from app.services import recommendation_service

router = APIRouter()


@router.get("", response_model=RecommendationPage)
@limiter.limit("30/minute")
async def recommendations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: Optional[str] = Query(default=None, max_length=100),
    lang: Literal["es", "en"] = "es",
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await recommendation_service.page(user_id, lang, cursor, limit)


@router.post("/dismiss", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
async def dismiss(request: Request, data: DismissIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    await recommendation_service.dismiss(user_id, data.movie_id, data.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/dismiss/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def undismiss(movie_id: str = Path(pattern=r"^\d{1,10}$"), user_id: uuid.UUID = Depends(get_current_user_id)):
    recommendation_service.undismiss(user_id, movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
