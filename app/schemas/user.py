from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import uuid

# Datos base compartidos
class UserBase(BaseModel):
    email: EmailStr
    username: str
    first_name: str
    last_name: str

# Datos para REGISTRARSE (Recibimos password plana)
class UserCreate(UserBase):
    password: str

# Datos para MOSTRAR (Devolvemos ID y fecha, pero NO el password)
class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
    status: bool
    
    class Config:
        from_attributes = True
class UserVerify(BaseModel):
    email: EmailStr
    code: str        