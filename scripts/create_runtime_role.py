"""Activa el rol movie_api_runtime (creado por la migración 0002) y escribe
DATABASE_URL_RUNTIME en .env. No imprime contraseñas.

Uso:  python -m scripts.create_runtime_role
Con DB_TARGET=dev en .env usa DATABASE_URL_DEV y escribe DATABASE_URL_RUNTIME_DEV.
Si no existe la contraseña del rol (DB_RUNTIME_PASSWORD[_DEV]), la genera.
"""
import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from dotenv import dotenv_values, set_key
from psycopg import sql

ENV_PATH = Path(".env")
ROLE = "movie_api_runtime"


def main() -> None:
    env = dotenv_values(ENV_PATH)
    suffix = "_DEV" if env.get("DB_TARGET") == "dev" else ""
    owner_url = env["DATABASE_URL" + suffix].replace("postgresql+psycopg2://", "postgresql://")
    password = env.get("DB_RUNTIME_PASSWORD" + suffix) or secrets.token_urlsafe(32)

    with psycopg.connect(owner_url, prepare_threshold=None) as conn:
        conn.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {} CONNECTION LIMIT 40").format(
                sql.Identifier(ROLE), sql.Literal(password)
            )
        )

    parts = urlsplit(owner_url)
    host = parts.netloc.split("@", 1)[1]
    runtime_url = urlunsplit(parts._replace(netloc=f"{ROLE}:{quote(password, safe='')}@{host}"))

    set_key(str(ENV_PATH), "DB_RUNTIME_PASSWORD" + suffix, password, quote_mode="never")
    set_key(str(ENV_PATH), "DATABASE_URL_RUNTIME" + suffix, runtime_url, quote_mode="never")
    print(f"Rol {ROLE} activado. DATABASE_URL_RUNTIME{suffix} escrita en .env (host {parts.hostname}).")


if __name__ == "__main__":
    main()
