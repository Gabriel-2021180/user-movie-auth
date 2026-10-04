from datetime import datetime, timezone
from typing import Optional

from app.core import security
from app.core.errors import APIError
from app.core.rate_limit import wait_text
from app.repositories import security_repository

# Bloqueo por email (exista o no la cuenta): la respuesta es idéntica en ambos casos, así
# no se puede averiguar qué emails están registrados. 3 intentos libres y luego esperas
# crecientes: 5, 15, 30 min, 1, 2, 4, 8 h y 24 h (ver api._lock_minutes en la migración 0006).
FREE_ATTEMPTS = 3


def invalid_credentials(attempts_left: Optional[int] = None) -> APIError:
    message = "Email o contraseña incorrectos."
    extra = {}
    if attempts_left is not None:
        extra["attempts_left"] = attempts_left
        if attempts_left == 0:
            message += " Si vuelves a fallar, bloquearemos el acceso temporalmente."
        elif attempts_left == 1:
            message += " Te queda 1 intento antes de un bloqueo temporal."
        elif attempts_left == 2:
            message += " Te quedan 2 intentos antes de un bloqueo temporal."
    return APIError(401, "invalid_credentials", message, extra=extra)


def locked(until: datetime, failures: int) -> APIError:
    seconds = max(1, int((until - datetime.now(timezone.utc)).total_seconds()))
    return APIError(
        423, "account_locked",
        f"Bloqueamos el acceso temporalmente por {failures} intentos fallidos de contraseña. "
        f"Podrás intentar de nuevo en {wait_text(seconds)}. Cada nuevo error aumenta el tiempo de espera.",
        extra={
            "reason": "too_many_failed_attempts",
            "failed_attempts": failures,
            "retry_after_seconds": seconds,
            "locked_until": until.isoformat(),
        },
        headers={"Retry-After": str(seconds)},
    )


def ensure_not_locked(email: str) -> None:
    status = security_repository.login_throttle_status(security.login_throttle_key(email))
    if status and status["locked_until"]:
        # Mismo tiempo de respuesta que una verificación real
        security.burn_password_check()
        raise locked(status["locked_until"], status["failures"])


def register_failure(email: str) -> APIError:
    """Cuenta el fallo y devuelve el error a lanzar (423 si empieza un bloqueo, si no 401)."""
    row = security_repository.login_throttle_fail(security.login_throttle_key(email))
    if row["locked_until"]:
        return locked(row["locked_until"], row["failures"])
    return invalid_credentials(max(0, FREE_ATTEMPTS - row["failures"]))


def clear(email: str) -> None:
    security_repository.login_throttle_clear(security.login_throttle_key(email))
