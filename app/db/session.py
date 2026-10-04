from typing import Optional

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

# --- ENGINE DE v1 (usuario dueño de la BD) ---
# pool_pre_ping=True: verifica que la conexión a Neon siga viva antes de usarla.
# Se retira junto con v1.
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)


def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


# --- ENGINE DE v2 (rol movie_api_runtime: solo EXECUTE sobre el esquema api) ---

def _psycopg3_url(url: str) -> str:
    for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_runtime_engine: Optional[Engine] = None


def get_runtime_engine() -> Engine:
    global _runtime_engine
    if _runtime_engine is None:
        if not settings.DATABASE_URL_RUNTIME:
            raise RuntimeError("DATABASE_URL_RUNTIME no está configurada")
        _runtime_engine = create_engine(
            _psycopg3_url(settings.DATABASE_URL_RUNTIME),
            echo=False,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            # El pooler de Neon (PgBouncer) y los prepared statements no se llevan bien
            connect_args={"prepare_threshold": None},
        )
    return _runtime_engine
