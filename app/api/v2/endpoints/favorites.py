import uuid

from fastapi import APIRouter, Depends, Path, Request, Response, status

from app.api.v2.deps import PageParams, created_or_ok, get_current_user_id
from app.core.limiter import limiter
from app.schemas.v2.library import MovieIn, MovieItem, Page, PersonIn, PersonItem
from app.services import library_service

router = APIRouter()

_TMDB_ID = Path(pattern=r"^\d{1,10}$")


@router.get("", response_model=Page[MovieItem])
def list_favorites(page: PageParams = Depends(), user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.favorites(user_id, page.cursor, page.limit)


@router.post("", response_model=MovieItem, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_favorite(request: Request, response: Response, data: MovieIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    item, created = library_service.add_favorite(user_id, data)
    created_or_ok(response, created)
    return item


@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(movie_id: str = _TMDB_ID, user_id: uuid.UUID = Depends(get_current_user_id)):
    library_service.remove_favorite(user_id, movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/people", response_model=Page[PersonItem])
def list_people(page: PageParams = Depends(), user_id: uuid.UUID = Depends(get_current_user_id)):
    return library_service.people(user_id, page.cursor, page.limit)


@router.post("/people", response_model=PersonItem, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_person(request: Request, response: Response, data: PersonIn, user_id: uuid.UUID = Depends(get_current_user_id)):
    item, created = library_service.add_person(user_id, data)
    created_or_ok(response, created)
    return item


@router.delete("/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_person(person_id: str = _TMDB_ID, user_id: uuid.UUID = Depends(get_current_user_id)):
    library_service.remove_person(user_id, person_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
