import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    username: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.]{3,30}$")
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    # bio: null o "" la borra; si no se envía, no cambia
    bio: Optional[str] = Field(default=None, max_length=280)
    banner_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    favorite_genres: Optional[List[int]] = Field(default=None, max_length=20)

    @field_validator("favorite_genres")
    @classmethod
    def valid_genres(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        if v is None:
            return None
        if any(g < 1 or g > 1_000_000 for g in v):
            raise ValueError("ID de género inválido")
        return list(dict.fromkeys(v))


class PublicProfile(BaseModel):
    username: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    banner_color: Optional[str] = None
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
