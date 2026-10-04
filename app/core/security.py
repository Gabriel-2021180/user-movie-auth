import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

# argon2id para hashes nuevos; los bcrypt existentes se verifican y se migran al iniciar sesión
_ph = PasswordHasher()
# Hash de relleno para igualar el tiempo de respuesta cuando el email no existe
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))


# --- CONTRASEÑAS ---

def get_password_hash(password: str) -> str:
    return _ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica contra argon2 o contra bcrypt (hashes heredados de passlib)."""
    if not hashed_password:
        return False
    if hashed_password.startswith("$argon2"):
        try:
            return _ph.verify(hashed_password, plain_password)
        except (VerificationError, InvalidHashError):
            return False
    if hashed_password.startswith("$2"):
        pw = plain_password.encode("utf-8")
        if len(pw) > 72:  # bcrypt solo usa 72 bytes; bcrypt>=5 lanza error
            return False
        try:
            return bcrypt.checkpw(pw, hashed_password.encode("utf-8"))
        except ValueError:
            return False
    return False


def password_needs_rehash(hashed_password: str) -> bool:
    if not hashed_password.startswith("$argon2"):
        return True
    return _ph.check_needs_rehash(hashed_password)


def burn_password_check() -> None:
    """Gasta el mismo tiempo que una verificación real (evita enumerar emails por tiempo)."""
    verify_password("invalid-password", _DUMMY_HASH)


# --- CLAVES DERIVADAS ---

def _derive_key(label: str) -> bytes:
    base = (settings.JWT_SECRET or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(base, label.encode("utf-8"), hashlib.sha256).digest()


# --- CÓDIGOS POR EMAIL ---

def generate_numeric_code(digits: int = 6) -> str:
    return str(secrets.randbelow(10 ** digits)).zfill(digits)


def hash_code(purpose: str, email: str, code: str) -> bytes:
    """HMAC del código: aunque se filtre la BD no se pueden probar los 10^6 códigos sin la clave."""
    msg = f"{purpose}:{email.lower()}:{code}".encode("utf-8")
    return hmac.new(_derive_key("email-code-v1"), msg, hashlib.sha256).digest()


# --- LÍMITES Y BLOQUEOS (en BD solo se guarda el HMAC, nunca la IP ni el email) ---

def login_throttle_key(email: str) -> bytes:
    return hmac.new(_derive_key("login-throttle-v1"), email.lower().encode("utf-8"), hashlib.sha256).digest()


def rate_limit_key(scope: str, kind: str, value: str) -> bytes:
    msg = f"{scope}:{kind}:{value.lower()}".encode("utf-8")
    return hmac.new(_derive_key("rate-limit-v1"), msg, hashlib.sha256).digest()


# --- REFRESH TOKENS (opacos; en BD solo se guarda su hash) ---

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


# --- ACCESS TOKENS v2 ---

def create_access_token_v2(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=settings.ACCESS_TOKEN_TTL_SECONDS),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _derive_key("jwt-access-v2"), algorithm="HS256")


def decode_access_token_v2(token: str) -> dict:
    """Lanza jwt.PyJWTError si el token no es válido."""
    claims = jwt.decode(
        token,
        _derive_key("jwt-access-v2"),
        algorithms=["HS256"],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


# --- ACCESS TOKENS v1 (sin cambios de comportamiento hasta retirar v1) ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
