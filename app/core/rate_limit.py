from typing import Dict, Optional, Tuple

from app.core import security
from app.core.config import settings
from app.core.errors import APIError
from app.repositories import security_repository

# Límites de auth guardados en la BD: valen igual con varias instancias de Vercel.
# (máximo, ventana en segundos) por IP real del cliente y, si aplica, por email o usuario.
_Rule = Tuple[int, int]
RULES: Dict[str, Dict[str, _Rule]] = {
    "signup": {"ip": (10, 3600), "email": (5, 3600)},
    "verify": {"ip": (30, 600), "email": (10, 600)},
    "login": {"ip": (30, 600), "email": (15, 600)},
    "refresh": {"ip": (60, 60)},
    "logout": {"ip": (60, 60)},
    "forgot": {"ip": (10, 3600), "email": (3, 3600)},
    "reset": {"ip": (20, 600), "email": (10, 600)},
    "reactivate": {"ip": (20, 600), "email": (10, 600)},
    "delete_me": {"user": (5, 3600)},
    "export": {"user": (3, 86400)},
}


def wait_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} segundos"
    minutes = -(-seconds // 60)
    if minutes < 60:
        return f"{minutes} minuto{'s' if minutes != 1 else ''}"
    hours = -(-minutes // 60)
    return f"{hours} hora{'s' if hours != 1 else ''}"


def enforce(scope: str, ip: Optional[str] = None, email: Optional[str] = None, user: Optional[str] = None) -> None:
    """Cuenta la solicitud y lanza 429 si alguno de los límites del scope se superó."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    subjects = {"ip": ip, "email": email, "user": user}
    for kind, (max_hits, window) in RULES[scope].items():
        value = subjects.get(kind)
        if not value:
            continue
        row = security_repository.rate_limit_hit(security.rate_limit_key(scope, kind, value), window, max_hits)
        if not row["allowed"]:
            wait = int(row["retry_after"])
            raise APIError(
                429, "rate_limited",
                f"Demasiadas solicitudes. Intenta de nuevo en {wait_text(wait)}.",
                extra={"retry_after_seconds": wait},
                headers={"Retry-After": str(wait)},
            )
