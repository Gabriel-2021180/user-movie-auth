from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import uuid

class Favorite(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Relación con el Usuario (Foreign Key)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    
    # Datos de la Película (Cacheamos esto para no llamar a TMDB siempre)
    movie_id: str = Field(index=True) # El ID de TMDB (ej: "550")
    title: str
    poster: Optional[str] = None
    year: Optional[str] = None
    
    # Metadatos
    added_at: datetime = Field(default_factory=datetime.utcnow)
    status: bool = Field(default=True) # Por si quieres "borrado lógico"