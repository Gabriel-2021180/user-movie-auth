import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.db import procedures

logger = logging.getLogger(__name__)

# Cliente de TMDB con caché temporal en la BD (tmdb_cache, con TTL: lo exigen los
# términos de TMDB). Si TMDB falla o tarda, se devuelve None y el recomendador
# sigue con lo que tenga: nunca rompe la respuesta al usuario.

LANGUAGES = {"es": "es-ES", "en": "en-US"}
_TIMEOUT = httpx.Timeout(5.0)


def _cache_key(path: str, params: Dict[str, Any]) -> str:
    query = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"tmdb:{path}?{query}"


def _auth() -> tuple[Dict[str, str], Dict[str, str]]:
    if settings.TMDB_READ_TOKEN:
        return {"Authorization": f"Bearer {settings.TMDB_READ_TOKEN}"}, {}
    if settings.TMDB_API_KEY:
        return {}, {"api_key": settings.TMDB_API_KEY}
    raise RuntimeError("TMDB no está configurado (TMDB_READ_TOKEN o TMDB_API_KEY)")


async def get(
    client: httpx.AsyncClient, path: str, params: Dict[str, Any], ttl_seconds: Optional[int] = None
) -> Optional[dict]:
    key = _cache_key(path, params)
    cached = await asyncio.to_thread(procedures.call_scalar, "api.tmdb_cache_get", p_key=key)
    if cached is not None:
        return cached

    headers, auth_params = _auth()
    try:
        r = await client.get(f"{settings.TMDB_BASE_URL}{path}", params={**params, **auth_params}, headers=headers)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("TMDB %s falló: %s", path, type(e).__name__)
        return None

    await asyncio.to_thread(
        procedures.call, "api.tmdb_cache_put",
        p_key=key, p_payload=data, p_ttl_seconds=ttl_seconds or settings.TMDB_CACHE_TTL_SECONDS,
    )
    return data


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT)
