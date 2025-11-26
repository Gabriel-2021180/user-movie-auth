from datetime import datetime, timedelta
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

# Configuración de seguridad para contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña plana coincide con su hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Convierte una contraseña plana en un hash seguro."""
    return pwd_context.hash(password)

# --- MANEJO DE TOKENS (NUEVO) ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un Token JWT firmado.
    data: Diccionario con los datos a guardar (ej: ID de usuario).
    expires_delta: Tiempo extra de vida del token.
    """
    to_encode = data.copy()
    
    # Calculamos cuándo expira
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Usamos el tiempo por defecto del config (30 min)
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Añadimos la fecha de expiración al token
    to_encode.update({"exp": expire})
    
    # Firmamos el token con nuestra CLAVE SECRETA
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return encoded_jwt