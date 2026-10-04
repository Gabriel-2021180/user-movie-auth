import uuid

from sqlalchemy import RowMapping

from app.core import security
from app.core.config import settings
from app.core.errors import APIError
from app.repositories import user_repository
from app.schemas.v2.library import OnboardingIn
from app.schemas.v2.user import LegalCurrent, ProfilePatch, PublicProfile, UserMe, UserStats


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
            watched=row["watched_count"],
            watchlist=row["watchlist_count"],
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


def update_profile(user_id: uuid.UUID, data: ProfilePatch) -> UserMe:
    sent = data.model_fields_set
    row = user_repository.update_profile(
        user_id, data.username, data.first_name, data.last_name,
        "bio" in sent, data.bio or None, data.banner_color, data.favorite_genres,
    )
    status = row["status"]
    if status == "username_taken":
        raise APIError(409, "username_taken", "Ese nombre de usuario ya está en uso.", fields={"username": "En uso"})
    if status == "name_change_too_soon":
        raise APIError(
            429, "name_change_too_soon",
            f"Solo puedes cambiar tu nombre o usuario cada 14 días. Faltan {row['days_left']} días.",
            extra={"days_left": row["days_left"]},
        )
    if status == "color_limit":
        raise APIError(429, "color_change_limit", "Has alcanzado el límite de 3 cambios de color por día.")
    if status != "ok":
        raise APIError(404, "user_not_found", "Usuario no encontrado")
    return get_me(user_id)


def public_profile(username: str) -> PublicProfile:
    row = user_repository.get_public(username)
    if row is None:
        raise APIError(404, "user_not_found", "Usuario no encontrado")
    return PublicProfile(
        username=row["username"],
        bio=row["bio"],
        banner_color=row["banner_color"],
        created_at=row["created_at"],
        stats=UserStats(
            favorites=row["favorites_count"],
            reviews=row["reviews_count"],
            watched=row["watched_count"],
            watchlist=row["watchlist_count"],
            avg_rating=float(row["avg_rating"]) if row["avg_rating"] is not None else None,
        ),
    )


def complete_onboarding(user_id: uuid.UUID, data: OnboardingIn) -> UserMe:
    user_repository.complete_onboarding(
        user_id,
        data.genres,
        [m.model_dump() for m in data.seed_movies],
        [p.model_dump(include={"person_id", "name", "photo", "job"}) for p in data.seed_people],
    )
    return get_me(user_id)
