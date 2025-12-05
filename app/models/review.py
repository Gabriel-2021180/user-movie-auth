from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
import uuid

# Importamos con TYPE_CHECKING para evitar errores de importación circular
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.movie import Movie

class Review(SQLModel, table=True):
    # CAMBIO IMPORTANTE: Usamos UUID en lugar de int
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Relación con Usuario
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    
    # Relación con Película
    movie_id: str = Field(foreign_key="movie.id", nullable=False)
    
    # Contenido
    rating: int = Field(ge=1, le=5) 
    content: str = Field(max_length=1000)
    sentiment: str 
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relaciones
    user: "User" = Relationship() # Quitamos back_populates si user.py no tiene la relación
    movie: "Movie" = Relationship(back_populates="reviews")