import uuid

from sqlalchemy import RowMapping

from app.core import security
from app.core.config import settings
from app.core.errors import APIError
from app.repositories import user_repository
from app.schemas.v2.user import LegalCurrent, UserMe, UserStats


def to_user_me(row: RowMapping) -> UserMe:
    needs_consent = (
        row["terms_version"] != settings.LEGAL_TERMS_VERSION
        or row["privacy_version"] != settings.LEGAL_PRIVACY_VERSION
    )
    return UserMe(
        id=row["id"],
        email=row["email"],
        username=row["username"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        avatar_url=None,  # avatares pospuestos
        bio=row["bio"],
        banner_color=row["banner_color"],
        favorite_genres=list(row["favorite_genres"] or []),
        onboarding_completed=row["onboarding_completed"],
        needs_consent=needs_consent,
        created_at=row["created_at"],
        stats=UserStats(
            favorites=row["favorites_count"],
            reviews=row["reviews_count"],
            watched=0,  # listas: siguiente etapa
            watchlist=0,
            avg_rating=float(row["avg_rating"]) if row["avg_rating"] is not None else None,
        ),
    )


def get_me(user_id: uuid.UUID) -> UserMe:
    row = user_repository.get_me(user_id)
    if row is None:
        raise APIError(404, "user_not_found", "Usuario no encontrado")
    return to_user_me(row)


def legal_current() -> LegalCurrent:
    return LegalCurrent(
        terms_version=settings.LEGAL_TERMS_VERSION,
        privacy_version=settings.LEGAL_PRIVACY_VERSION,
        terms_url=settings.LEGAL_TERMS_URL,
        privacy_url=settings.LEGAL_PRIVACY_URL,
    )


def record_consent(user_id: uuid.UUID, terms_version: str, privacy_version: str, ip: str) -> None:
    if terms_version != settings.LEGAL_TERMS_VERSION or privacy_version != settings.LEGAL_PRIVACY_VERSION:
        raise APIError(
            422, "legal_version_mismatch", "Debes aceptar la versión vigente de Términos y Privacidad.",
            extra={"terms_version": settings.LEGAL_TERMS_VERSION, "privacy_version": settings.LEGAL_PRIVACY_VERSION},
        )
    user_repository.record_consent(user_id, terms_version, privacy_version, ip)


def deactivate(user_id: uuid.UUID, password: str) -> None:
    row = user_repository.get_auth_by_id(user_id)
    if row is None or not security.verify_password(password, row["hashed_password"]):
        if row is not None:
            user_repository.register_login_failure(user_id)
        raise APIError(401, "invalid_credentials", "Contraseña incorrecta")
    user_repository.deactivate(user_id)
