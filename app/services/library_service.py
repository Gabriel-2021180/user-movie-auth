import uuid
from typing import Optional, Tuple

from app.core.errors import APIError
from app.repositories import library_repository, list_repository, review_repository
from app.schemas.v2.library import (
    ListDetail, ListIn, ListPatch, ListSummary, MovieIn, MovieItem, Page, PersonIn, PersonItem,
    WatchedIn, WatchedItem,
)
from app.schemas.v2.review import MovieState, ReviewOut

MAX_LISTS_PER_USER = 100
MAX_ITEMS_PER_LIST = 500

# Las altas son idempotentes: devuelven (item, created) y el endpoint responde 201 o 200.


# --- FAVORITOS ---

def favorites(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page[MovieItem]:
    rows, nxt = library_repository.favorites(user_id, cursor, limit)
    return Page[MovieItem](items=[MovieItem(**r) for r in rows], next_cursor=nxt)


def add_favorite(user_id: uuid.UUID, m: MovieIn) -> Tuple[MovieItem, bool]:
    row = library_repository.favorite_add(user_id, m.movie_id, m.title, m.poster, m.year)
    return MovieItem(**{k: row[k] for k in MovieItem.model_fields}), row["created"]


def remove_favorite(user_id: uuid.UUID, movie_id: str) -> None:
    library_repository.favorite_remove(user_id, movie_id)


# --- PERSONAS ---

def people(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page[PersonItem]:
    rows, nxt = library_repository.people(user_id, cursor, limit)
    return Page[PersonItem](items=[PersonItem(**r) for r in rows], next_cursor=nxt)


def add_person(user_id: uuid.UUID, p: PersonIn) -> Tuple[PersonItem, bool]:
    row = library_repository.person_add(user_id, p.person_id, p.name, p.photo, p.job, p.known_for)
    return PersonItem(**{k: row[k] for k in PersonItem.model_fields}), row["created"]


def remove_person(user_id: uuid.UUID, person_id: str) -> None:
    library_repository.person_remove(user_id, person_id)


# --- VER DESPUÉS / VISTAS ---

def watchlist(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page[MovieItem]:
    rows, nxt = library_repository.watchlist(user_id, cursor, limit)
    return Page[MovieItem](items=[MovieItem(**r) for r in rows], next_cursor=nxt)


def add_watchlist(user_id: uuid.UUID, m: MovieIn) -> Tuple[MovieItem, bool]:
    row = library_repository.watchlist_add(user_id, m.movie_id, m.title, m.poster, m.year)
    return MovieItem(**{k: row[k] for k in MovieItem.model_fields}), row["created"]


def remove_watchlist(user_id: uuid.UUID, movie_id: str) -> None:
    library_repository.watchlist_remove(user_id, movie_id)


def watched(user_id: uuid.UUID, cursor: Optional[str], limit: int) -> Page[WatchedItem]:
    rows, nxt = library_repository.watched(user_id, cursor, limit)
    return Page[WatchedItem](items=[WatchedItem(**r) for r in rows], next_cursor=nxt)


def add_watched(user_id: uuid.UUID, m: WatchedIn) -> Tuple[WatchedItem, bool]:
    row = library_repository.watched_add(user_id, m.movie_id, m.title, m.poster, m.year, m.watched_at)
    return WatchedItem(**{k: row[k] for k in WatchedItem.model_fields}), row["created"]


def remove_watched(user_id: uuid.UUID, movie_id: str) -> None:
    library_repository.watched_remove(user_id, movie_id)


# --- LISTAS PERSONALIZADAS ---

def _list_not_found() -> APIError:
    return APIError(404, "list_not_found", "Lista no encontrada")


def lists(user_id: uuid.UUID) -> list:
    return [ListSummary(**r) for r in list_repository.all_for_user(user_id)]


def get_list(viewer_id: uuid.UUID, list_id: uuid.UUID, cursor: Optional[str], limit: int) -> ListDetail:
    meta = list_repository.get(viewer_id, list_id)
    if meta is None:
        raise _list_not_found()
    rows, nxt = list_repository.items(list_id, cursor, limit)
    return ListDetail(**meta, items=[MovieItem(**r) for r in rows], next_cursor=nxt)


def create_list(user_id: uuid.UUID, data: ListIn) -> ListDetail:
    row = list_repository.create(user_id, data.name, data.description, data.is_public, MAX_LISTS_PER_USER)
    if row["status"] == "limit_reached":
        raise APIError(409, "list_limit", f"Máximo {MAX_LISTS_PER_USER} listas por usuario.")
    if row["status"] == "name_taken":
        raise APIError(409, "list_name_taken", "Ya tienes una lista con ese nombre.", fields={"name": "En uso"})
    return get_list(user_id, row["list_id"], None, 1)


def update_list(user_id: uuid.UUID, list_id: uuid.UUID, data: ListPatch) -> ListSummary:
    sent = data.model_fields_set
    status = list_repository.update(
        user_id, list_id, data.name, "description" in sent, data.description or None, data.is_public
    )
    if status == "not_found":
        raise _list_not_found()
    if status == "name_taken":
        raise APIError(409, "list_name_taken", "Ya tienes una lista con ese nombre.", fields={"name": "En uso"})
    meta = list_repository.get(user_id, list_id)
    return ListSummary(**{k: meta[k] for k in ListSummary.model_fields})


def delete_list(user_id: uuid.UUID, list_id: uuid.UUID) -> None:
    if not list_repository.delete(user_id, list_id):
        raise _list_not_found()


def add_list_item(user_id: uuid.UUID, list_id: uuid.UUID, m: MovieIn) -> bool:
    status = list_repository.item_add(user_id, list_id, m.movie_id, m.title, m.poster, m.year, MAX_ITEMS_PER_LIST)
    if status == "not_found":
        raise _list_not_found()
    if status == "limit_reached":
        raise APIError(409, "list_full", f"Una lista admite hasta {MAX_ITEMS_PER_LIST} películas.")
    return status == "ok"


def remove_list_item(user_id: uuid.UUID, list_id: uuid.UUID, movie_id: str) -> None:
    if list_repository.item_remove(user_id, list_id, movie_id) == "not_found":
        raise _list_not_found()


# --- ESTADO DE UNA PELÍCULA ---

def movie_state(user_id: uuid.UUID, movie_id: str) -> MovieState:
    row = library_repository.movie_state(user_id, movie_id)
    review = review_repository.get(row["review_id"]) if row["review_id"] else None
    return MovieState(
        favorite=row["is_favorite"],
        in_watchlist=row["in_watchlist"],
        watched_at=row["watched_at"],
        my_review=ReviewOut(**review) if review else None,
        in_lists=list(row["in_lists"] or []),
    )
