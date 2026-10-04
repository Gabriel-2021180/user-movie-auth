import uuid
from typing import Optional

from sqlalchemy import RowMapping

from app.db import procedures

# --- CÓDIGOS POR EMAIL ---


def signup_start(email: str, username: str, code_hash: bytes, payload: dict, ttl_minutes: int) -> str:
    return procedures.call_scalar(
        "api.signup_start",
        p_email=email,
        p_username=username,
        p_code_hash=code_hash,
        p_payload=payload,
        p_ttl_minutes=ttl_minutes,
    )


def signup_complete(
    email: str, code_hash: bytes, max_attempts: int, terms_version: str, privacy_version: str, ip: str
) -> RowMapping:
    return procedures.call_one(
        "api.signup_complete",
        p_email=email,
        p_code_hash=code_hash,
        p_max_attempts=max_attempts,
        p_terms_version=terms_version,
        p_privacy_version=privacy_version,
        p_ip=ip,
    )


def password_reset_start(email: str, code_hash: bytes, ttl_minutes: int) -> RowMapping:
    return procedures.call_one(
        "api.password_reset_start", p_email=email, p_code_hash=code_hash, p_ttl_minutes=ttl_minutes
    )


def password_reset_complete(email: str, code_hash: bytes, max_attempts: int, new_hash: str) -> str:
    return procedures.call_scalar(
        "api.password_reset_complete",
        p_email=email,
        p_code_hash=code_hash,
        p_max_attempts=max_attempts,
        p_new_hash=new_hash,
    )


# --- REFRESH TOKENS ---


def refresh_issue(
    user_id: uuid.UUID, family_id: Optional[uuid.UUID], token_hash: bytes, ttl_seconds: int,
    user_agent: Optional[str], ip: str,
) -> None:
    procedures.call(
        "api.refresh_issue",
        p_user_id=user_id,
        p_family_id=family_id,
        p_token_hash=token_hash,
        p_ttl_seconds=ttl_seconds,
        p_user_agent=user_agent,
        p_ip=ip,
    )


def refresh_rotate(
    old_hash: bytes, new_hash: bytes, ttl_seconds: int, user_agent: Optional[str], ip: str
) -> RowMapping:
    return procedures.call_one(
        "api.refresh_rotate",
        p_old_hash=old_hash,
        p_new_hash=new_hash,
        p_ttl_seconds=ttl_seconds,
        p_user_agent=user_agent,
        p_ip=ip,
    )


def refresh_revoke(token_hash: bytes) -> None:
    procedures.call("api.refresh_revoke", p_token_hash=token_hash)


def refresh_revoke_all(user_id: uuid.UUID) -> None:
    procedures.call("api.refresh_revoke_all", p_user_id=user_id)
