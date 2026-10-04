import base64
import json
from datetime import datetime
from typing import Any, List, Optional, Tuple

from sqlalchemy import RowMapping

from app.core.errors import APIError
from app.db import procedures

# Paginación por cursor (keyset): el cursor es opaco para el front y codifica
# (fecha, id) del último elemento devuelto. Las funciones de BD reciben
# p_cursor_ts / p_cursor_id / p_limit y ordenan por (fecha DESC, id DESC).

DEFAULT_LIMIT = 30
MAX_LIMIT = 100


def encode_cursor(ts: datetime, item_id: Any) -> str:
    raw = json.dumps({"t": ts.isoformat(), "i": str(item_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: Optional[str]) -> Tuple[Optional[datetime], Optional[str]]:
    if not cursor:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        ts = datetime.fromisoformat(data["t"])
        if ts.tzinfo is None:
            raise ValueError("cursor sin zona horaria")
        return ts, str(data["i"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise APIError(422, "invalid_cursor", "Cursor de paginación inválido")


def encode_offset_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode().rstrip("=")


def decode_offset_cursor(cursor: Optional[str]) -> int:
    """Cursor por posición, para listas calculadas al vuelo (recomendaciones)."""
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        offset = int(json.loads(base64.urlsafe_b64decode(padded))["o"])
        if offset < 0 or offset > 10_000:
            raise ValueError
        return offset
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise APIError(422, "invalid_cursor", "Cursor de paginación inválido")


def fetch_page(
    fn: str, ts_field: str, id_field: str, cursor: Optional[str], limit: int, **params: Any
) -> Tuple[List[RowMapping], Optional[str]]:
    ts, cursor_id = decode_cursor(cursor)
    rows = procedures.call(fn, **params, p_cursor_ts=ts, p_cursor_id=cursor_id, p_limit=limit + 1)
    if len(rows) <= limit:
        return rows, None
    last = rows[limit - 1]
    return rows[:limit], encode_cursor(last[ts_field], last[id_field])
