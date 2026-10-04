from typing import Annotated, List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # Configuración general (no sensible)
    PROJECT_NAME: str = "Movie Identity Service"
    API_V1_STR: str = "/api/v1"
    API_V2_STR: str = "/api/v2"
    # /docs y /openapi.json solo se publican con ENVIRONMENT=development
    ENVIRONMENT: str = "production"

    # --- VARIABLES SENSIBLES (Se leen del .env) ---

    # Clave de firma de los tokens de v1
    SECRET_KEY: str

    # Conexión con el usuario dueño de la BD: la usan v1 y las migraciones
    DATABASE_URL: str
    # Conexión con el rol de mínimos privilegios (solo EXECUTE sobre el esquema api): la usa v2
    DATABASE_URL_RUNTIME: Optional[str] = None

    # Email
    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str

    # JWT v1 (se mantiene hasta retirar v1)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    # JWT v2: clave propia, access token corto + refresh token rotativo
    JWT_SECRET: Optional[str] = None
    JWT_ISSUER: str = "movie-auth-api"
    JWT_AUDIENCE: str = "movie-explorer"
    ACCESS_TOKEN_TTL_SECONDS: int = 900
    REFRESH_TOKEN_TTL_SECONDS: int = 60 * 60 * 24 * 30

    # Códigos enviados por email
    VERIFICATION_CODE_TTL_MINUTES: int = 10
    RESET_CODE_TTL_MINUTES: int = 15
    CODE_MAX_ATTEMPTS: int = 5

    # Baja de cuenta
    ACCOUNT_GRACE_DAYS: int = 90

    # BFF (Next.js): secreto compartido que habilita X-Client-IP
    BFF_SHARED_SECRET: Optional[str] = None
    REQUIRE_BFF_SECRET: bool = True

    # Cron de Vercel para la purga
    CRON_SECRET: Optional[str] = None

    # CORS: solo el origen del front (lista separada por comas)
    CORS_ORIGINS: Annotated[List[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Legal
    LEGAL_TERMS_VERSION: str = "2026-10-01"
    LEGAL_PRIVACY_VERSION: str = "2026-10-01"
    LEGAL_TERMS_URL: str = "/legal/terminos"
    LEGAL_PRIVACY_URL: str = "/legal/privacidad"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def docs_enabled(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"


settings = Settings()
