import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.v2.user import UserMe

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")

# Contraseñas nuevas (registro y reset). Además se rechazan las que aparecen en filtraciones (HIBP).
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


def _check_password_policy(v: str) -> str:
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("La contraseña debe tener al menos una letra y un número")
    return v


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SignupIn(_In):
    email: EmailStr = Field(max_length=254)
    username: str
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    accepted_terms_version: str = Field(min_length=1, max_length=32)
    accepted_privacy_version: str = Field(min_length=1, max_length=32)

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("Usuario de 3 a 30 caracteres: letras, números, '_' o '.'")
        return v

    _password = field_validator("password")(_check_password_policy)


class VerifyIn(_In):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class LoginIn(_In):
    email: EmailStr
    # Sin política aquí: hay contraseñas antiguas que no la cumplen
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(_In):
    refresh_token: str = Field(min_length=20, max_length=200)


class ForgotPasswordIn(_In):
    email: EmailStr


class ResetPasswordIn(_In):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    _password = field_validator("new_password")(_check_password_policy)


class ReactivateIn(_In):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Tokens(BaseModel):
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int
    token_type: str = "bearer"


class AuthOut(BaseModel):
    user: UserMe
    tokens: Tokens


class MessageOut(BaseModel):
    message: str
