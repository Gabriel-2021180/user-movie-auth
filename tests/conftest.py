"""Configuración de tests.

Las variables se fijan ANTES de importar la app, así los tests nunca leen la BD real del .env.
Los tests de integración necesitan un Postgres desechable:

    docker run -d --name movie-auth-testdb -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17
    TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres pytest
"""
import os
import re
from urllib.parse import urlsplit

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
RUNTIME_PASSWORD = "runtime_test_pw"


def _runtime_url(owner_url: str) -> str:
    parts = urlsplit(owner_url)
    host = parts.netloc.split("@", 1)[1]
    return f"{parts.scheme}://movie_api_runtime:{RUNTIME_PASSWORD}@{host}{parts.path}"


os.environ.update({
    "ENVIRONMENT": "test",
    # Fuerza DATABASE_URL (BD de test) aunque el .env tenga DB_TARGET=dev
    "DB_TARGET": "prod",
    "SECRET_KEY": "test-secret-key-" + "x" * 32,
    "JWT_SECRET": "test-jwt-secret-" + "y" * 32,
    "DATABASE_URL": TEST_DB or "postgresql://invalid:invalid@127.0.0.1:1/invalid",
    "DATABASE_URL_RUNTIME": _runtime_url(TEST_DB) if TEST_DB else "",
    "SMTP_SERVER": "localhost",
    "SMTP_PORT": "25",
    "SMTP_USER": "noreply@example.com",
    "SMTP_PASSWORD": "unused",
    "BFF_SHARED_SECRET": "bff-test-secret",
    "REQUIRE_BFF_SECRET": "true",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.core.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402

BFF_HEADERS = {"X-BFF-Secret": "bff-test-secret", "X-Client-IP": "203.0.113.7"}


@pytest.fixture
def client():
    limiter.reset()
    limiter.enabled = False
    with TestClient(app) as c:
        yield c
    limiter.enabled = True


@pytest.fixture
def outbox(monkeypatch):
    """Captura los emails en vez de enviarlos."""
    sent = []

    def fake_send(email_to, subject, body):
        sent.append({"to": email_to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr("app.services.email_service._send_html", fake_send)
    return sent


def extract_code(mail: dict) -> str:
    return re.search(r">(\d{6})</h1>", mail["body"]).group(1)


@pytest.fixture(scope="session")
def db_ready():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL no configurada")
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlmodel import SQLModel

    import app.models.favorite  # noqa: F401
    import app.models.movie  # noqa: F401
    import app.models.password_reset  # noqa: F401
    import app.models.pending_user  # noqa: F401
    import app.models.review  # noqa: F401
    import app.models.user  # noqa: F401
    from app.db.session import engine

    # Esquema de v1 tal como lo creó SQLModel en producción
    SQLModel.metadata.create_all(engine)
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        # Igualar los defaults que tiene la tabla "user" en producción (agregados con ALTER en v1)
        conn.execute("""
            ALTER TABLE "user"
                ALTER COLUMN banner_color DROP NOT NULL, ALTER COLUMN banner_color SET DEFAULT '#a16207',
                ALTER COLUMN daily_color_changes DROP NOT NULL, ALTER COLUMN daily_color_changes SET DEFAULT 0,
                ALTER COLUMN failed_login_attempts DROP NOT NULL, ALTER COLUMN failed_login_attempts SET DEFAULT 0
        """)
    command.upgrade(Config("alembic.ini"), "head")
    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(f"ALTER ROLE movie_api_runtime WITH LOGIN PASSWORD '{RUNTIME_PASSWORD}'")
    return TEST_DB
