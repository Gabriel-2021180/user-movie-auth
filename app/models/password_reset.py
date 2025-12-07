# app/models/password_reset.py
from sqlmodel import SQLModel, Field
from pydantic import EmailStr
from datetime import datetime
import uuid

class PasswordReset(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(index=True)
    code: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)