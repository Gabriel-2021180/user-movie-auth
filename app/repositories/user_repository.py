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


def get_public(username: str) -> Optional[RowMapping]:
    return procedures.call_one("api.user_public", p_username=username)


def update_profile(
    user_id: uuid.UUID, username: Optional[str], first_name: Optional[str], last_name: Optional[str],
    set_bio: bool, bio: Optional[str], banner_color: Optional[str], favorite_genres: Optional[list],
) -> RowMapping:
    return procedures.call_one(
        "api.user_update_profile", p_user_id=user_id, p_username=username, p_first_name=first_name,
        p_last_name=last_name, p_set_bio=set_bio, p_bio=bio, p_banner_color=banner_color,
        p_favorite_genres=favorite_genres,
    )


def complete_onboarding(user_id: uuid.UUID, genres: list, seed_movies: list, seed_people: list) -> None:
    procedures.call(
        "api.onboarding_complete", p_user_id=user_id, p_genres=genres,
        p_seed_movies=seed_movies, p_seed_people=seed_people,
    )
