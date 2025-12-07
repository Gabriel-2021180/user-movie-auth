from sqlmodel import SQLModel, Field, Relationship
from typing import Optional,List
from datetime import datetime
import uuid

# Tabla de Usuario basada en tu diagrama
class User(SQLModel, table=True):
    # ID único tipo UUID (ej: 550e8400-e29b-41d4-a716-446655440000)
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # Datos Personales
    first_name: str  # nombre
    last_name: str   # apellido
    
    # Datos de Cuenta
    username: str = Field(unique=True, index=True) # nombre de usuario
    email: str = Field(unique=True, index=True)
    hashed_password: str # password (encriptada)
    
    failed_login_attempts: int = Field(default=0)  # Contador de fallos
    locked_until: Optional[datetime] = None
    # Metadatos
    created_at: datetime = Field(default_factory=datetime.utcnow) # fecha_registro (automática)
    status: bool = Field(default=True) # Estado (Activo/Inactivo)
    last_profile_update: Optional[datetime] = None 
    banner_color: str = Field(default="#a16207")
    daily_color_changes: int = Field(default=0)
    last_color_change_at: Optional[datetime] = None
    reviews: List["Review"] = Relationship(back_populates="user")
  