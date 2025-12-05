from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import uuid # <--- Importar uuid

class ReviewCreate(BaseModel):
    movie_id: str
    movie_title: str
    movie_poster: Optional[str] = None
    movie_year: Optional[str] = "N/A"
    rating: int
    content: str

# Esquema para lectura
class ReviewRead(BaseModel):
    id: uuid.UUID # <--- CAMBIO: Ahora es UUID
    user_id: uuid.UUID # <--- CAMBIO: También es UUID
    movie_id: str
    username: str
    
    # Datos extra para el perfil
    movie_title: Optional[str] = None
    movie_poster: Optional[str] = None
    
    rating: int
    content: str
    sentiment: str
    created_at: datetime

    class Config:
        from_attributes = True