import uuid
from typing import List, Optional, Tuple

from sqlalchemy import RowMapping

from app.db import procedures
from app.db.pagination import fetch_page

Page = Tuple[List[RowMapping], Optional[str]]


def by_movie(movie_id: str, cursor: Optional[str], limit: int) -> Page:
    return fetch_page("api.review_list_by_movie", "created_at", "id", cursor, limit, p_movie_id=movie_id)


def movie_summary(movie_id: str) -> RowMapping:
    return procedures.call_one("api.review_movie_summary", p_movie_id=movie_id)


def by_user(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page:
    return fetch_page("api.review_list_by_user", "created_at", "id", cursor, limit, p_user_id=user_id)


def get(review_id: uuid.UUID) -> Optional[RowMapping]:
    return procedures.call_one("api.review_get", p_review_id=review_id)


def create(
    user_id: uuid.UUID, movie_id: str, movie_title: str, movie_poster: Optional[str],
    movie_year: Optional[str], rating: int, content: str,
) -> RowMapping:
    return procedures.call_one(
        "api.review_create", p_user_id=user_id, p_movie_id=movie_id, p_movie_title=movie_title,
        p_movie_poster=movie_poster, p_movie_year=movie_year, p_rating=rating, p_content=content,
    )


def update(user_id: uuid.UUID, review_id: uuid.UUID, rating: Optional[int], content: Optional[str]) -> str:
    return procedures.call_scalar(
        "api.review_update", p_user_id=user_id, p_review_id=review_id, p_rating=rating, p_content=content
    )


def delete(user_id: uuid.UUID, review_id: uuid.UUID) -> str:
    return procedures.call_scalar("api.review_delete", p_user_id=user_id, p_review_id=review_id)
