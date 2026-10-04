import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import RowMapping

from app.core import security
from app.core.config import settings
from app.core.errors import APIError
from app.repositories import auth_repository, user_repository
from app.schemas.v2.auth import (
    AuthOut, ForgotPasswordIn, LoginIn, ReactivateIn, ResetPasswordIn, SignupIn, Tokens, VerifyIn,
)
from app.integrations import hibp
from app.services import login_guard, user_service
from app.services.email_service import EmailService

SIGNUP_MESSAGE = "Te enviamos un código de verificación. Revisa tu correo."
FORGOT_MESSAGE = "Si el correo está registrado, recibirás un código."


def _breached(field: str) -> APIError:
    message = "Esta contraseña apareció en filtraciones de datos públicas. Elige otra."
    return APIError(422, "password_breached", message, fields={field: message})


def _reactivate_until(row: RowMapping) -> Optional[datetime]:
    if not row["deactivated_at"]:
        return None
    return row["deactivated_at"] + timedelta(days=settings.ACCOUNT_GRACE_DAYS)


def _issue_tokens(user_id: uuid.UUID, user_agent: Optional[str], ip: str) -> Tokens:
    refresh = security.generate_refresh_token()
    auth_repository.refresh_issue(
        user_id, None, security.hash_refresh_token(refresh), settings.REFRESH_TOKEN_TTL_SECONDS, user_agent, ip
    )
    return Tokens(
        access_token=security.create_access_token_v2(user_id),
        access_expires_in=settings.ACCESS_TOKEN_TTL_SECONDS,
        refresh_token=refresh,
        refresh_expires_in=settings.REFRESH_TOKEN_TTL_SECONDS,
    )


def _auth_out(user_id: uuid.UUID, user_agent: Optional[str], ip: str) -> AuthOut:
    tokens = _issue_tokens(user_id, user_agent, ip)
    return AuthOut(user=user_service.get_me(user_id), tokens=tokens)


def _check_password_or_fail(email: str, password: str) -> RowMapping:
    """Verificación común de login/reactivación: tiempo constante y bloqueo creciente por email.

    Un email inexistente recibe exactamente las mismas respuestas (401 y luego 423).
    """
    login_guard.ensure_not_locked(email)
    row = user_repository.get_auth_by_email(email)
    if row is None:
        security.burn_password_check()
        raise login_guard.register_failure(email)
    if not security.verify_password(password, row["hashed_password"]):
        raise login_guard.register_failure(email)
    login_guard.clear(email)
    if not row["is_enabled"]:
        raise APIError(403, "account_disabled", "Esta cuenta está deshabilitada.")
    return row


def _code_error(status: str) -> APIError:
    if status == "invalid_code":
        return APIError(400, "invalid_code", "El código es incorrecto.")
    if status == "too_many_attempts":
        return APIError(400, "code_attempts_exceeded", "Demasiados intentos. Solicita un código nuevo.")
    return APIError(400, "code_expired", "El código expiró o no existe. Solicita uno nuevo.")


def _check_legal_versions(terms: str, privacy: str) -> None:
    if terms != settings.LEGAL_TERMS_VERSION or privacy != settings.LEGAL_PRIVACY_VERSION:
        raise APIError(
            422, "legal_version_mismatch", "Debes aceptar la versión vigente de Términos y Privacidad.",
            extra={"terms_version": settings.LEGAL_TERMS_VERSION, "privacy_version": settings.LEGAL_PRIVACY_VERSION},
        )


# --- REGISTRO ---

async def signup(data: SignupIn) -> str:
    _check_legal_versions(data.accepted_terms_version, data.accepted_privacy_version)
    if await hibp.is_breached(data.password):
        raise _breached("password")
    email = data.email.lower()
    code = security.generate_numeric_code()
    payload = {
        "username": data.username,
        "first_name": data.first_name,
        "last_name": data.last_name,
        # argon2 y la BD son bloqueantes: fuera del event loop
        "hashed_password": await asyncio.to_thread(security.get_password_hash, data.password),
    }
    status = await asyncio.to_thread(
        auth_repository.signup_start,
        email, data.username, security.hash_code("signup", email, code), payload,
        settings.VERIFICATION_CODE_TTL_MINUTES,
    )
    if status == "username_taken":
        raise APIError(409, "username_taken", "Ese nombre de usuario ya está en uso.", fields={"username": "En uso"})
    if status == "email_taken":
        # Misma respuesta que un registro normal: no se revela qué emails existen
        await EmailService.send_account_exists_notice(email)
        return SIGNUP_MESSAGE
    if status == "too_soon":
        raise APIError(429, "code_recently_sent", "Ya enviamos un código hace poco. Espera un minuto.",
                       headers={"Retry-After": "60"})
    if not await EmailService.send_signup_code(email, data.username, code, settings.VERIFICATION_CODE_TTL_MINUTES):
        raise APIError(503, "email_unavailable", "No pudimos enviar el correo. Intenta de nuevo.")
    return SIGNUP_MESSAGE


def verify(data: VerifyIn, user_agent: Optional[str], ip: str) -> AuthOut:
    email = data.email.lower()
    row = auth_repository.signup_complete(
        email, security.hash_code("signup", email, data.code), settings.CODE_MAX_ATTEMPTS,
        settings.LEGAL_TERMS_VERSION, settings.LEGAL_PRIVACY_VERSION, ip,
    )
    if row["status"] == "already_registered":
        raise APIError(409, "already_registered", "Este email o usuario ya fue registrado.")
    if row["status"] != "ok":
        raise _code_error(row["status"])
    return _auth_out(row["user_id"], user_agent, ip)


# --- SESIÓN ---

def login(data: LoginIn, user_agent: Optional[str], ip: str) -> AuthOut:
    row = _check_password_or_fail(data.email, data.password)
    new_hash = security.get_password_hash(data.password) if security.password_needs_rehash(row["hashed_password"]) else None
    user_repository.register_login_success(row["id"], new_hash)

    if row["account_status"] == "deactivated":
        until = _reactivate_until(row)
        if until is None or until < datetime.now(timezone.utc):
            raise login_guard.invalid_credentials()
        raise APIError(
            409, "account_deactivated", "Tu cuenta está dada de baja. Puedes reactivarla.",
            extra={"reactivate_until": until.isoformat()},
        )
    return _auth_out(row["id"], user_agent, ip)


def refresh(refresh_token: str, user_agent: Optional[str], ip: str) -> Tokens:
    new_refresh = security.generate_refresh_token()
    row = auth_repository.refresh_rotate(
        security.hash_refresh_token(refresh_token), security.hash_refresh_token(new_refresh),
        settings.REFRESH_TOKEN_TTL_SECONDS, user_agent, ip,
    )
    if row["status"] == "reused":
        raise APIError(401, "refresh_reused", "Sesión revocada por seguridad. Inicia sesión de nuevo.")
    if row["status"] != "ok":
        raise APIError(401, "invalid_refresh", "Sesión expirada. Inicia sesión de nuevo.")
    return Tokens(
        access_token=security.create_access_token_v2(row["user_id"]),
        access_expires_in=settings.ACCESS_TOKEN_TTL_SECONDS,
        refresh_token=new_refresh,
        refresh_expires_in=settings.REFRESH_TOKEN_TTL_SECONDS,
    )


def logout(refresh_token: str) -> None:
    auth_repository.refresh_revoke(security.hash_refresh_token(refresh_token))


def logout_all(user_id: uuid.UUID) -> None:
    auth_repository.refresh_revoke_all(user_id)


def reactivate(data: ReactivateIn, user_agent: Optional[str], ip: str) -> AuthOut:
    row = _check_password_or_fail(data.email, data.password)
    status = user_repository.reactivate(row["id"], settings.ACCOUNT_GRACE_DAYS)
    if status == "expired":
        raise login_guard.invalid_credentials()
    if status == "not_deactivated":
        raise APIError(409, "not_deactivated", "La cuenta ya está activa. Inicia sesión normalmente.")
    user_repository.register_login_success(row["id"], None)
    return _auth_out(row["id"], user_agent, ip)


# --- CONTRASEÑA ---

async def forgot_password(data: ForgotPasswordIn) -> str:
    email = data.email.lower()
    code = security.generate_numeric_code()
    row = await asyncio.to_thread(
        auth_repository.password_reset_start,
        email, security.hash_code("password_reset", email, code), settings.RESET_CODE_TTL_MINUTES
    )
    if row["status"] == "ok":
        await EmailService.send_reset_code(email, row["username"], code, settings.RESET_CODE_TTL_MINUTES)
    # Siempre la misma respuesta (no revela si el email existe)
    return FORGOT_MESSAGE


async def reset_password(data: ResetPasswordIn) -> str:
    # Antes de gastar un intento del código: si la contraseña está filtrada, puede reintentar
    if await hibp.is_breached(data.new_password):
        raise _breached("new_password")
    email = data.email.lower()
    new_hash = await asyncio.to_thread(security.get_password_hash, data.new_password)
    status = await asyncio.to_thread(
        auth_repository.password_reset_complete,
        email, security.hash_code("password_reset", email, data.code), settings.CODE_MAX_ATTEMPTS, new_hash,
    )
    if status != "ok":
        raise _code_error(status)
    # Demostró ser dueño del email: se levanta el bloqueo de login
    await asyncio.to_thread(login_guard.clear, email)
    return "Contraseña actualizada. Ya puedes iniciar sesión."
