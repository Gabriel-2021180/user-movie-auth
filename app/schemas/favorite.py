from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

# Lo que el Frontend envía para agregar a favoritos
class FavoriteCreate(BaseModel):
    movie_id: str
    title: str
    poster: Optional[str] = None
    year: Optional[str] = None

# Lo que la API responde
class FavoriteRead(BaseModel):
    id: uuid.UUID
    movie_id: str
    title: str
    poster: Optional[str]
    year: Optional[str]
    added_at: datetime