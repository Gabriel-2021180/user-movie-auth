from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# reasons: {type:"because_liked"|"onboarding_seed"|"because_watched", movie_id, title}
#        | {type:"because_rated", movie_id, title, rating}
#        | {type:"because_person", person_id, name}
#        | {type:"genre_match", genre_id, genre_name}
#        | {type:"popular"}  (usuarios sin señales todavía)


class RecommendationItem(BaseModel):
    movie_id: str
    title: str
    poster: Optional[str] = None
    year: Optional[str] = None
    score: float
    reasons: List[dict]


class RecommendationPage(BaseModel):
    items: List[RecommendationItem]
    next_cursor: Optional[str] = None
    generated_at: datetime


class DismissIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movie_id: str = Field(pattern=r"^\d{1,10}$")
    reason: Literal["not_interested", "already_seen"] = "not_interested"
