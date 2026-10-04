import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.v2.library import _check_image


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    movie_id: str = Field(pattern=r"^\d{1,10}$")
    movie_title: str = Field(min_length=1, max_length=300)
    movie_poster: Optional[str] = Field(default=None, max_length=500)
    movie_year: Optional[str] = Field(default=None, max_length=10)
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=1000)

    _poster = field_validator("movie_poster")(_check_image)


class ReviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    content: Optional[str] = Field(default=None, min_length=1, max_length=1000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    movie_id: str
    movie_title: Optional[str] = None
    movie_poster: Optional[str] = None
    rating: int
    content: str
    sentiment: str
    created_at: datetime
    updated_at: datetime


class ReviewSummary(BaseModel):
    count: int
    avg_rating: Optional[float] = None


class MovieReviewsPage(BaseModel):
    items: List[ReviewOut]
    next_cursor: Optional[str] = None
    summary: ReviewSummary


class MovieState(BaseModel):
    favorite: bool
    in_watchlist: bool
    watched_at: Optional[datetime] = None
    my_review: Optional[ReviewOut] = None
    in_lists: List[uuid.UUID]
    dismissed: bool = False  # se conecta en la etapa de recomendaciones
