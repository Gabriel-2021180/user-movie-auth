import uuid
from typing import List

from fastapi import APIRouter, Depends, Path, Request, Response, status

from app.api.v2.deps import PageParams, created_or_ok, get_current_user_id
from app.core.limiter import limiter
from app.schemas.v2.library import (
    ListDetail, ListIn, ListPatch, ListSummary, MovieIn, MovieItem, Page, WatchedIn, WatchedItem,
)
from app.services import library_service

router = APIRouter()

_TMDB_ID = Path(pattern=r"^\d{1,10}$")


# --- VER DESPUÉS ---

@router.get("/watchlist", response_model=Page[MovieItem])
def list_watchlist(page: PageParams = Depends(), user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.watchlist(user_id, page.cursor, page.limit)


@router.post("/watchlist", response_model=MovieItem, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_watchlist(request: Request, response: Response, data: MovieIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    item, created = library_service.add_watchlist(user_id, data)
    created_or_ok(response, created)
    return item


@router.delete("/watchlist/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watchlist(movie_id: str = _TMDB_ID, user_id: uuid.UUID = Depends(get_current_user_id)):
    library_service.remove_watchlist(user_id, movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- VISTAS ---

@router.get("/watched", response_model=Page[WatchedItem])
def list_watched(page: PageParams = Depends(), user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.watched(user_id, page.cursor, page.limit)


@router.post("/watched", response_model=WatchedItem, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_watched(request: Request, response: Response, data: WatchedIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    item, created = library_service.add_watched(user_id, data)
    created_or_ok(response, created)
    return item


@router.delete("/watched/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_watched(movie_id: str = _TMDB_ID, user_id: uuid.UUID = Depends(get_current_user_id)):
    library_service.remove_watched(user_id, movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- LISTAS PERSONALIZADAS ---

@router.get("", response_model=List[ListSummary])
def my_lists(user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.lists(user_id)


@router.post("", response_model=ListDetail, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_list(request: Request, data: ListIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.create_list(user_id, data)


@router.get("/{list_id}", response_model=ListDetail)
def get_list(list_id: uuid.UUID, page: PageParams = Depends(), user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.get_list(user_id, list_id, page.cursor, page.limit)


@router.patch("/{list_id}", response_model=ListSummary)
def update_list(list_id: uuid.UUID, data: ListPatch, user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.update_list(user_id, list_id, data)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: uuid.UUID, user_id: uuid.UUID = Depends(get_current_user_id)):
    library_service.delete_list(user_id, list_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{list_id}/items", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_list_item(
    request: Request, response: Response, list_id: uuid.UUID, data: MovieIn,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    created = library_service.add_list_item(user_id, list_id, data)
    created_or_ok(response, created)
    return {"movie_id": data.movie_id, "list_id": str(list_id)}


@router.delete("/{list_id}/items/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_list_item(list_id: uuid.UUID, movie_id: str = _TMDB_ID, user_id: uuid.UUID = Depends(get_current_user_id)):
    library_service.remove_list_item(user_id, list_id, movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
