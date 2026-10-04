import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import RowMapping

from app.db import procedures
from app.db.pagination import fetch_page

Page = Tuple[List[RowMapping], Optional[str]]

# --- FAVORITOS ---


def favorites(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page:
    return fetch_page("api.favorite_list", "added_at", "movie_id", cursor, limit, p_user_id=user_id)


def favorite_add(user_id: uuid.UUID, movie_id: str, title: str, poster: Optional[str], year: Optional[str]) -> RowMapping:
    return procedures.call_one(
        "api.favorite_add", p_user_id=user_id, p_movie_id=movie_id, p_title=title, p_poster=poster, p_year=year
    )


def favorite_remove(user_id: uuid.UUID, movie_id: str) -> None:
    procedures.call("api.favorite_remove", p_user_id=user_id, p_movie_id=movie_id)


# --- PERSONAS FAVORITAS ---


def people(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page:
    return fetch_page("api.favorite_person_list", "created_at", "person_id", cursor, limit, p_user_id=user_id)


def person_add(
    user_id: uuid.UUID, person_id: str, name: str, photo: Optional[str], job: str, known_for: Optional[str]
) -> RowMapping:
    return procedures.call_one(
        "api.favorite_person_add", p_user_id=user_id, p_person_id=person_id, p_name=name,
        p_photo=photo, p_job=job, p_known_for=known_for,
    )


def person_remove(user_id: uuid.UUID, person_id: str) -> None:
    procedures.call("api.favorite_person_remove", p_user_id=user_id, p_person_id=person_id)


# --- VER DESPUÉS / VISTAS ---


def watchlist(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page:
    return fetch_page("api.watchlist_list", "added_at", "movie_id", cursor, limit, p_user_id=user_id)


def watchlist_add(user_id: uuid.UUID, movie_id: str, title: str, poster: Optional[str], year: Optional[str]) -> RowMapping:
    return procedures.call_one(
        "api.watchlist_add", p_user_id=user_id, p_movie_id=movie_id, p_title=title, p_poster=poster, p_year=year
    )


def watchlist_remove(user_id: uuid.UUID, movie_id: str) -> None:
    procedures.call("api.watchlist_remove", p_user_id=user_id, p_movie_id=movie_id)


def watched(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page:
    return fetch_page("api.watched_list", "watched_at", "movie_id", cursor, limit, p_user_id=user_id)


def watched_add(
    user_id: uuid.UUID, movie_id: str, title: str, poster: Optional[str], year: Optional[str],
    watched_at: Optional[datetime],
) -> RowMapping:
    return procedures.call_one(
        "api.watched_add", p_user_id=user_id, p_movie_id=movie_id, p_title=title, p_poster=poster,
        p_year=year, p_watched_at=watched_at,
    )


def watched_remove(user_id: uuid.UUID, movie_id: str) -> None:
    procedures.call("api.watched_remove", p_user_id=user_id, p_movie_id=movie_id)


# --- ESTADO DE UNA PELÍCULA ---


def movie_state(user_id: uuid.UUID, movie_id: str) -> RowMapping:
    return procedures.call_one("api.movie_state", p_user_id=user_id, p_movie_id=movie_id)
