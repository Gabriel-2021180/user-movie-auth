from pydantic import BaseModel
from typing import Optional

# Lo que devolvemos al usuario cuando hace login
class Token(BaseModel):
    access_token: str
    token_type: str # Generalmente "bearer"

# Lo que hay DENTRO del token (cuando lo desencriptamos)
class TokenPayload(BaseModel):
    sub: Optional[str] = None # Subject (usualmente el ID del usuario)