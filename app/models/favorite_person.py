# app/models/favorite_person.py

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime
import uuid
# Importamos User solo como string para evitar referencias circulares si lo necesitas
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.user import User

class FavoritePerson(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Relación con el Usuario
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    
    # Datos de la Persona (Actor/Director)
    person_id: str = Field(index=True) # El ID de TMDB (ej: "12345")
    name: str
    photo: Optional[str] = None
    job: str # "Acting" o "Directing" para saber qué es
    known_for: Optional[str] = None # Películas famosas (texto simple)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relación (Opcional, ayuda a navegar desde User)
    user: Optional["User"] = Relationship(back_populates="favorite_people")