from typing import Optional

from sqlalchemy import RowMapping

from app.db import procedures

# --- LÍMITE DE SOLICITUDES ---


def rate_limit_hit(key: bytes, window_seconds: int, max_hits: int) -> RowMapping:
    return procedures.call_one(
        "api.rate_limit_hit", p_key=key, p_window_seconds=window_seconds, p_max=max_hits
    )


# --- BLOQUEO DE LOGIN POR EMAIL ---


def login_throttle_status(email_key: bytes) -> Optional[RowMapping]:
    return procedures.call_one("api.login_throttle_status", p_email_key=email_key)


def login_throttle_fail(email_key: bytes) -> RowMapping:
    return procedures.call_one("api.login_throttle_fail", p_email_key=email_key)


def login_throttle_clear(email_key: bytes) -> None:
    procedures.call("api.login_throttle_clear", p_email_key=email_key)
