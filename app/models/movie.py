from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class Movie(SQLModel, table=True):
    # Usamos el ID de TMDB como Primary Key (es un string, ej: "550")
    # Así evitamos duplicados automáticamente.
    id: str = Field(primary_key=True, index=True)
    
    title: str
    poster: str
    year: str
    
    # --- ESTADÍSTICAS PROPIAS (Opcional pero recomendado) ---
    # Guardamos esto para no tener que calcular el promedio cada vez que alguien entra
    vote_count: int = Field(default=0)
    vote_sum: int = Field(default=0)
    
    # Propiedad calculada para el promedio (no se guarda en BD, se calcula al vuelo si quieres)
    # O puedes guardar un campo 'average_rating' y actualizarlo.
    
    # Relación: Una película tiene muchas reseñas
    reviews: List["Review"] = Relationship(back_populates="movie")