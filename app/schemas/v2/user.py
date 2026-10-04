import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserStats(BaseModel):
    favorites: int
    reviews: int
    watched: int
    watchlist: int
    avg_rating: Optional[float] = None


class UserMe(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    banner_color: Optional[str] = None
    favorite_genres: List[int]
    onboarding_completed: bool
    needs_consent: bool
    created_at: datetime
    stats: UserStats


class DeleteMeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=128)


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    terms_version: str = Field(min_length=1, max_length=32)
    privacy_version: str = Field(min_length=1, max_length=32)


class LegalCurrent(BaseModel):
    terms_version: str
    privacy_version: str
    terms_url: str
    privacy_url: str
