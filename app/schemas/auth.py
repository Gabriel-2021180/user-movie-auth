# app/schemas/auth.py
from pydantic import BaseModel, EmailStr

# 1. Para pedir el código
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

# 2. Para cambiar la contraseña
class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str