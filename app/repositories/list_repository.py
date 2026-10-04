import uuid
from typing import List, Optional, Tuple

from sqlalchemy import RowMapping

from app.db import procedures
from app.db.pagination import fetch_page


def all_for_user(user_id: uuid.UUID) -> List[RowMapping]:
    return procedures.call("api.list_all", p_user_id=user_id)


def get(viewer_id: uuid.UUID, list_id: uuid.UUID) -> Optional[RowMapping]:
    return procedures.call_one("api.list_get", p_viewer_id=viewer_id, p_list_id=list_id)


def create(user_id: uuid.UUID, name: str, description: Optional[str], is_public: bool, max_lists: int) -> RowMapping:
    return procedures.call_one(
        "api.list_create", p_user_id=user_id, p_name=name, p_description=description,
        p_is_public=is_public, p_max_lists=max_lists,
    )


def update(
    user_id: uuid.UUID, list_id: uuid.UUID, name: Optional[str], set_description: bool,
    description: Optional[str], is_public: Optional[bool],
) -> str:
    return procedures.call_scalar(
        "api.list_update", p_user_id=user_id, p_list_id=list_id, p_name=name,
        p_set_description=set_description, p_description=description, p_is_public=is_public,
    )


def delete(user_id: uuid.UUID, list_id: uuid.UUID) -> bool:
    return procedures.call_scalar("api.list_delete", p_user_id=user_id, p_list_id=list_id)


def items(list_id: uuid.UUID, cursor: Optional[str], limit: int) -> Tuple[List[RowMapping], Optional[str]]:
    return fetch_page("api.list_items", "added_at", "movie_id", cursor, limit, p_list_id=list_id)


def item_add(
    user_id: uuid.UUID, list_id: uuid.UUID, movie_id: str, title: str, poster: Optional[str],
    year: Optional[str], max_items: int,
) -> str:
    return procedures.call_scalar(
        "api.list_item_add", p_user_id=user_id, p_list_id=list_id, p_movie_id=movie_id, p_title=title,
        p_poster=poster, p_year=year, p_max_items=max_items,
    )


def item_remove(user_id: uuid.UUID, list_id: uuid.UUID, movie_id: str) -> str:
    return procedures.call_scalar("api.list_item_remove", p_user_id=user_id, p_list_id=list_id, p_movie_id=movie_id)
