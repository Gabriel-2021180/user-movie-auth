from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

class PendingRegistration(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Datos del usuario (esperando ser movidos)
    email: str = Field(index=True)
    username: str
    first_name: str
    last_name: str
    hashed_password: str
    
    # Seguridad del código
    verification_code: str
    expires_at: datetime