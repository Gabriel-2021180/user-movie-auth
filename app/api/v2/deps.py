import uuid
from typing import Optional

import jwt
from fastapi import Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import RowMapping

from app.core.client_ip import get_client_ip, is_trusted_bff
from app.core.config import settings
from app.core.errors import APIError
from app.core.security import decode_access_token_v2
from app.db.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.repositories import user_repository

_bearer = HTTPBearer(auto_error=False)


def require_bff(request: Request) -> None:
    """v2 solo acepta llamadas del BFF (header X-BFF-Secret)."""
    if settings.REQUIRE_BFF_SECRET and not is_trusted_bff(request):
        raise APIError(401, "bff_required", "Origen no autorizado")


def client_ip(request: Request) -> str:
    return get_client_ip(request)


def user_agent(request: Request) -> Optional[str]:
    ua = request.headers.get("x-client-user-agent") if is_trusted_bff(request) else None
    return (ua or request.headers.get("user-agent") or "")[:256] or None


def get_current_user_row(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> RowMapping:
    unauthorized = APIError(401, "invalid_token", "Token inválido o expirado",
                            headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = decode_access_token_v2(credentials.credentials)
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise unauthorized

    row = user_repository.get_me(user_id)
    if row is None or not row["is_enabled"] or row["account_status"] != "active":
        raise unauthorized
    # Tokens emitidos antes del último cambio de contraseña quedan invalidados
    changed = row["password_changed_at"]
    if changed is not None and claims["iat"] < int(changed.timestamp()):
        raise unauthorized
    return row


def get_current_user_id(row: RowMapping = Depends(get_current_user_row)) -> uuid.UUID:
    return row["id"]


class PageParams:
    """?cursor=...&limit=... para los listados paginados."""

    def __init__(
        self,
        cursor: Optional[str] = Query(default=None, max_length=200),
        limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ):
        self.cursor = cursor
        self.limit = limit


def created_or_ok(response: Response, created: bool) -> None:
    """Altas idempotentes: 201 si se creó, 200 si ya existía."""
    response.status_code = 201 if created else 200
