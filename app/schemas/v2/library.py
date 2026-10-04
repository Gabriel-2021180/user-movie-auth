import uuid
from datetime import datetime, timedelta, timezone
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

_TMDB_ID = r"^\d{1,10}$"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _check_image(v: Optional[str]) -> Optional[str]:
    # Ruta de TMDB ("/abc.jpg") o URL https; nunca javascript:, data:, etc.
    if v and not (v.startswith("/") or v.startswith("https://")):
        raise ValueError("Debe ser una ruta que empiece con '/' o una URL https")
    return v or None


class Page(BaseModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None


# --- PELÍCULAS ---

class MovieIn(_In):
    movie_id: str = Field(pattern=_TMDB_ID)
    title: str = Field(min_length=1, max_length=300)
    poster: Optional[str] = Field(default=None, max_length=500)
    year: Optional[str] = Field(default=None, max_length=10)

    _poster = field_validator("poster")(_check_image)


class MovieItem(BaseModel):
    movie_id: str
    title: str
    poster: Optional[str] = None
    year: Optional[str] = None
    added_at: datetime


class WatchedIn(MovieIn):
    watched_at: Optional[datetime] = None

    @field_validator("watched_at")
    @classmethod
    def not_in_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v > datetime.now(timezone.utc) + timedelta(days=1):
            raise ValueError("La fecha no puede estar en el futuro")
        return v


class WatchedItem(BaseModel):
    movie_id: str
    title: str
    poster: Optional[str] = None
    year: Optional[str] = None
    watched_at: datetime


# --- PERSONAS ---

class PersonIn(_In):
    person_id: str = Field(pattern=_TMDB_ID)
    name: str = Field(min_length=1, max_length=200)
    photo: Optional[str] = Field(default=None, max_length=500)
    job: str = Field(default="Acting", min_length=1, max_length=50)
    known_for: Optional[str] = Field(default=None, max_length=500)

    _photo = field_validator("photo")(_check_image)


class PersonItem(BaseModel):
    person_id: str
    name: str
    photo: Optional[str] = None
    job: str
    known_for: Optional[str] = None
    created_at: datetime


# --- LISTAS PERSONALIZADAS ---

class ListIn(_In):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    is_public: bool = False


class ListPatch(_In):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    is_public: Optional[bool] = None


class ListSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_public: bool
    item_count: int
    created_at: datetime
    updated_at: datetime


class ListDetail(ListSummary):
    owner_username: str
    is_owner: bool
    items: List[MovieItem]
    next_cursor: Optional[str] = None


# --- ONBOARDING ---

class OnboardingIn(_In):
    genres: List[int] = Field(min_length=3, max_length=20)
    seed_movies: List[MovieIn] = Field(min_length=3, max_length=20)
    seed_people: List[PersonIn] = Field(default_factory=list, max_length=20)

    @field_validator("genres")
    @classmethod
    def valid_genres(cls, v: List[int]) -> List[int]:
        if any(g < 1 or g > 1_000_000 for g in v):
            raise ValueError("ID de género inválido")
        return list(dict.fromkeys(v))
