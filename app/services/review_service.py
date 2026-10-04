import uuid
from typing import Optional

from app.core.errors import APIError
from app.repositories import review_repository
from app.schemas.v2.library import Page
from app.schemas.v2.review import MovieReviewsPage, ReviewIn, ReviewOut, ReviewPatch, ReviewSummary


def _status_error(status: str) -> APIError:
    if status == "forbidden":
        return APIError(403, "forbidden", "No puedes modificar esta reseña.")
    return APIError(404, "review_not_found", "Reseña no encontrada")


def by_movie(movie_id: str, cursor: Optional[str], limit: int) -> MovieReviewsPage:
    rows, nxt = review_repository.by_movie(movie_id, cursor, limit)
    summary = review_repository.movie_summary(movie_id)
    return MovieReviewsPage(
        items=[ReviewOut(**r) for r in rows],
        next_cursor=nxt,
        summary=ReviewSummary(
            count=summary["review_count"],
            avg_rating=float(summary["avg_rating"]) if summary["avg_rating"] is not None else None,
        ),
    )


def mine(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page[ReviewOut]:
    rows, nxt = review_repository.by_user(user_id, cursor, limit)
    return Page[ReviewOut](items=[ReviewOut(**r) for r in rows], next_cursor=nxt)


def create(user_id: uuid.UUID, data: ReviewIn) -> ReviewOut:
    row = review_repository.create(
        user_id, data.movie_id, data.movie_title, data.movie_poster, data.movie_year, data.rating, data.content
    )
    if row["status"] == "exists":
        raise APIError(409, "review_exists", "Ya escribiste una reseña para esta película.")
    return ReviewOut(**review_repository.get(row["review_id"]))


def update(user_id: uuid.UUID, review_id: uuid.UUID, data: ReviewPatch) -> ReviewOut:
    status = review_repository.update(user_id, review_id, data.rating, data.content)
    if status != "ok":
        raise _status_error(status)
    return ReviewOut(**review_repository.get(review_id))


def delete(user_id: uuid.UUID, review_id: uuid.UUID) -> None:
    status = review_repository.delete(user_id, review_id)
    if status != "ok":
        raise _status_error(status)
