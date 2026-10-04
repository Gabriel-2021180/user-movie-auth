import hashlib
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Have I Been Pwned (k-anonimidad): solo se envían los 5 primeros caracteres del SHA-1,
# nunca la contraseña ni su hash completo. Si el servicio falla, no se bloquea el registro.

_URL = "https://api.pwnedpasswords.com/range/{prefix}"
_TIMEOUT = httpx.Timeout(3.0)


async def is_breached(password: str) -> bool:
    if not settings.HIBP_ENABLED:
        return False
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(
                _URL.format(prefix=prefix),
                headers={"Add-Padding": "true", "User-Agent": "movie-auth-api"},
            )
            r.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("HIBP no disponible, se omite la verificación: %s", type(exc).__name__)
        return False
    for line in r.text.splitlines():
        candidate, _, count = line.partition(":")
        # Con Add-Padding llegan entradas falsas con conteo 0
        if candidate.strip() == suffix and count.strip() not in ("", "0"):
            return True
    return False
