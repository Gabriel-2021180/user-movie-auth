from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

# Los errores de v2 siempre tienen la forma {error: {code, message, fields?, ...extra}}.
# v1 conserva el formato por defecto de FastAPI ({detail}) para no romper el front actual.

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: Optional[Dict[str, str]] = None,
        extra: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.extra = extra or {}
        self.headers = headers


def _envelope(status_code: int, code: str, message: str, fields=None, extra=None, headers=None) -> JSONResponse:
    body: Dict[str, Any] = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


def _is_v2(request: Request) -> bool:
    return request.url.path.startswith(settings.API_V2_STR)


async def _api_error_handler(request: Request, exc: APIError):
    return _envelope(exc.status_code, exc.code, exc.message, exc.fields, exc.extra, exc.headers)


async def _http_error_handler(request: Request, exc: StarletteHTTPException):
    if not _is_v2(request):
        return await http_exception_handler(request, exc)
    code = _STATUS_CODES.get(exc.status_code, "error")
    message = exc.detail if isinstance(exc.detail, str) else "Error"
    return _envelope(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _validation_error_handler(request: Request, exc: RequestValidationError):
    if not _is_v2(request):
        return await request_validation_exception_handler(request, exc)
    fields: Dict[str, str] = {}
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        key = ".".join(loc) or "body"
        msg = str(err.get("msg", "Valor inválido"))
        # Pydantic antepone "Value error, " a los errores de validadores propios
        fields.setdefault(key, msg.removeprefix("Value error, "))
    return _envelope(422, "validation_error", "Datos inválidos", fields=fields)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    if not _is_v2(request):
        return _rate_limit_exceeded_handler(request, exc)
    return _envelope(429, "rate_limited", "Demasiadas solicitudes. Intenta más tarde.", headers={"Retry-After": "60"})


async def _unhandled_error_handler(request: Request, exc: Exception):
    # Nunca exponer detalles internos al cliente
    return _envelope(500, "internal_error", "Error interno del servidor")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
