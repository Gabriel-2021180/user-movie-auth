import uuid

from fastapi import APIRouter, Depends, Path, Request, Response, status

from app.api.v2.deps import PageParams, get_current_user_id
from app.core.limiter import limiter
from app.schemas.v2.library import Page
from app.schemas.v2.review import MovieReviewsPage, ReviewIn, ReviewOut, ReviewPatch
from app.services import review_service

router = APIRouter()


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_review(request: Request, data: ReviewIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    return review_service.create(user_id, data)


@router.get("/me", response_model=Page[ReviewOut])
def my_reviews(page: PageParams = Depends(), user_id: uuid.UUID = Depends(get_current_user_id)):
    return review_service.mine(user_id, page.cursor, page.limit)


# Pública (no requiere usuario, sí el secreto del BFF)
@router.get("/movie/{movie_id}", response_model=MovieReviewsPage)
def movie_reviews(movie_id: str = Path(pattern=r"^\d{1,10}$"), page: PageParams = Depends()):
    return review_service.by_movie(movie_id, page.cursor, page.limit)


@router.put("/{review_id}", response_model=ReviewOut)
@limiter.limit("30/minute")
def update_review(
    request: Request, review_id: uuid.UUID, data: ReviewPatch, user_id: uuid.UUID = Depends(get_current_user_id),
):
    return review_service.update(user_id, review_id, data)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: uuid.UUID, user_id: uuid.UUID = Depends(get_current_user_id)):
    review_service.delete(user_id, review_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
