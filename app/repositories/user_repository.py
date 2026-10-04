import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import RowMapping

from app.db import procedures


def get_me(user_id: uuid.UUID) -> Optional[RowMapping]:
    return procedures.call_one("api.user_me", p_user_id=user_id)


def get_auth_by_email(email: str) -> Optional[RowMapping]:
    return procedures.call_one("api.user_auth_by_email", p_email=email)


def get_auth_by_id(user_id: uuid.UUID) -> Optional[RowMapping]:
    return procedures.call_one("api.user_auth_by_id", p_user_id=user_id)


def register_login_failure(user_id: uuid.UUID) -> Optional[RowMapping]:
    return procedures.call_one("api.login_register_failure", p_user_id=user_id)


def register_login_success(user_id: uuid.UUID, new_hash: Optional[str]) -> None:
    procedures.call("api.login_register_success", p_user_id=user_id, p_new_hash=new_hash)


def deactivate(user_id: uuid.UUID) -> Optional[datetime]:
    return procedures.call_scalar("api.user_deactivate", p_user_id=user_id)


def reactivate(user_id: uuid.UUID, grace_days: int) -> str:
    return procedures.call_scalar("api.user_reactivate", p_user_id=user_id, p_grace_days=grace_days)


def record_consent(user_id: uuid.UUID, terms_version: str, privacy_version: str, ip: str) -> None:
    procedures.call(
        "api.consent_record",
        p_user_id=user_id,
        p_terms_version=terms_version,
        p_privacy_version=privacy_version,
        p_ip=ip,
    )
