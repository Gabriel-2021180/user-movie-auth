import uuid

from fastapi import APIRouter, Depends, Path

from app.api.v2.deps import get_current_user_id
from app.schemas.v2.review import MovieState
from app.services import library_service

router = APIRouter()


@router.get("/{movie_id}/state", response_model=MovieState)
def movie_state(movie_id: str = Path(pattern=r"^\d{1,10}$"), user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.movie_state(user_id, movie_id)
