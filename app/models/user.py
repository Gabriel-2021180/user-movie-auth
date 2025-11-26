from sqlmodel import SQLModel, Field
from typing import Optional
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
    
    # Metadatos
    created_at: datetime = Field(default_factory=datetime.utcnow) # fecha_registro (automática)
    status: bool = Field(default=True) # Estado (Activo/Inactivo)
    
  