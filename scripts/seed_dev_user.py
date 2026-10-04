"""Crea un usuario verificado en el branch DEV de Neon para probar el front de punta a punta.

    python -m scripts.seed_dev_user

Solo funciona con DB_TARGET=dev. Usa las mismas funciones de BD que el registro real
(signup_start + signup_complete), sin enviar email. Las credenciales se escriben en
.env.devuser (ignorado por git) y no se imprimen. Cada ejecución crea un usuario nuevo.
"""
import secrets
from pathlib import Path

from app.core import security
from app.core.config import settings
from app.repositories import auth_repository

OUT_PATH = Path(".env.devuser")


def main() -> None:
    if settings.DB_TARGET != "dev":
        raise SystemExit("Bloqueado: este script solo corre con DB_TARGET=dev (nunca en producción).")

    suffix = secrets.token_hex(4)
    email = f"dev_tester_{suffix}@example.com"
    username = f"dev_tester_{suffix}"
    # 12+ caracteres con letras y números; aleatoria, así que no aparece en filtraciones
    password = f"Dev{secrets.token_urlsafe(12)}9"
    code = security.generate_numeric_code()

    status = auth_repository.signup_start(
        email, username, security.hash_code("signup", email, code),
        {"username": username, "first_name": "Dev", "last_name": "Tester",
         "hashed_password": security.get_password_hash(password)},
        settings.VERIFICATION_CODE_TTL_MINUTES,
    )
    if status != "ok":
        raise SystemExit(f"signup_start devolvió {status}")
    row = auth_repository.signup_complete(
        email, security.hash_code("signup", email, code), settings.CODE_MAX_ATTEMPTS,
        settings.LEGAL_TERMS_VERSION, settings.LEGAL_PRIVACY_VERSION, "127.0.0.1",
    )
    if row["status"] != "ok":
        raise SystemExit(f"signup_complete devolvió {row['status']}")

    OUT_PATH.write_text(
        "# Usuario de prueba del branch DEV de Neon (no sirve en producción). No subir a git.\n"
        f"DEV_TEST_EMAIL={email}\nDEV_TEST_USERNAME={username}\nDEV_TEST_PASSWORD={password}\n",
        encoding="utf-8",
    )
    print(f"Usuario de dev creado ({username}). Credenciales en {OUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
