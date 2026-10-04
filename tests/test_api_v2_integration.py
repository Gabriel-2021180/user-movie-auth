"""Flujo completo de v2 contra un Postgres desechable (ver tests/conftest.py)."""
import time
import uuid

import bcrypt
import psycopg
import pytest

from app.core import rate_limit
from app.core.config import settings
from app.integrations import hibp
from tests.conftest import BFF_HEADERS, extract_code

pytestmark = pytest.mark.usefixtures("db_ready")

PASSWORD = "SecretaLarga123"


def _signup_payload(email: str, username: str, password: str = PASSWORD) -> dict:
    return {
        "email": email, "username": username, "first_name": "Ana", "last_name": "Test",
        "password": password,
        "accepted_terms_version": settings.LEGAL_TERMS_VERSION,
        "accepted_privacy_version": settings.LEGAL_PRIVACY_VERSION,
    }


def _register(client, outbox, email=None, username=None) -> dict:
    email = email or f"user_{uuid.uuid4().hex[:8]}@example.com"
    username = username or f"u_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/v2/auth/signup", headers=BFF_HEADERS, json=_signup_payload(email, username))
    assert r.status_code == 202, r.text
    code = extract_code(outbox[-1])
    r = client.post("/api/v2/auth/verify", headers=BFF_HEADERS, json={"email": email, "code": code})
    assert r.status_code == 201, r.text
    body = r.json()
    body["email"] = email
    return body


def _auth(token: str) -> dict:
    return {**BFF_HEADERS, "Authorization": f"Bearer {token}"}


def test_runtime_role_cannot_touch_tables(db_ready):
    from tests.conftest import _runtime_url
    with psycopg.connect(_runtime_url(db_ready)) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM public."user"')
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM api._consume_code('signup', 'a@b.c', '\\x00'::bytea, 5)")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE api.hack (id int)")


def test_signup_verify_me(client, outbox):
    auth = _register(client, outbox)
    me = client.get("/api/v2/users/me", headers=_auth(auth["tokens"]["access_token"]))
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == auth["email"]
    assert body["needs_consent"] is False
    assert body["avatar_url"] is None
    assert body["stats"] == {"favorites": 0, "reviews": 0, "watched": 0, "watchlist": 0, "avg_rating": None}
    assert auth["tokens"]["access_expires_in"] == 900


def test_signup_existing_email_does_not_leak(client, outbox):
    auth = _register(client, outbox)
    r = client.post("/api/v2/auth/signup", headers=BFF_HEADERS,
                    json=_signup_payload(auth["email"].upper(), f"u_{uuid.uuid4().hex[:8]}"))
    assert r.status_code == 202
    assert outbox[-1]["subject"] == "Intento de registro - FilmStack"


def test_signup_username_taken(client, outbox):
    auth = _register(client, outbox)
    r = client.post("/api/v2/auth/signup", headers=BFF_HEADERS,
                    json=_signup_payload("other@example.com", auth["user"]["username"].upper()))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "username_taken"


def test_wrong_code_attempts_are_limited(client, outbox):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/v2/auth/signup", headers=BFF_HEADERS, json=_signup_payload(email, f"u_{uuid.uuid4().hex[:8]}"))
    real = extract_code(outbox[-1])
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(settings.CODE_MAX_ATTEMPTS):
        r = client.post("/api/v2/auth/verify", headers=BFF_HEADERS, json={"email": email, "code": wrong})
        assert r.json()["error"]["code"] == "invalid_code"
    # Agotados los intentos, ni el código correcto sirve
    r = client.post("/api/v2/auth/verify", headers=BFF_HEADERS, json={"email": email, "code": real})
    assert r.json()["error"]["code"] == "code_attempts_exceeded"


def test_refresh_rotation_and_reuse_detection(client, outbox):
    auth = _register(client, outbox)
    old = auth["tokens"]["refresh_token"]
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": old})
    assert r.status_code == 200
    new = r.json()["refresh_token"]
    assert new != old
    # Reusar el viejo revoca toda la familia
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": old})
    assert r.json()["error"]["code"] == "refresh_reused"
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": new})
    assert r.json()["error"]["code"] == "refresh_reused"


def test_logout_revokes_refresh(client, outbox):
    auth = _register(client, outbox)
    rt = auth["tokens"]["refresh_token"]
    assert client.post("/api/v2/auth/logout", headers=BFF_HEADERS, json={"refresh_token": rt}).status_code == 204
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": rt})
    assert r.status_code == 401


def _fail_until_locked(client, email: str) -> dict:
    """3 intentos libres (401 con attempts_left 2, 1, 0) y el 4.º bloquea (423)."""
    for left in (2, 1, 0):
        r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "Mala1234"})
        err = r.json()["error"]
        assert r.status_code == 401 and err["code"] == "invalid_credentials"
        assert err["attempts_left"] == left
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "Mala1234"})
    assert r.status_code == 423
    return r.json()["error"]


def _expire_lock(db_url: str) -> None:
    with psycopg.connect(db_url) as conn:
        conn.execute("UPDATE login_throttle SET locked_until = now() - interval '1 second' WHERE locked_until > now()")


def test_login_and_progressive_lock(client, outbox, db_ready):
    auth = _register(client, outbox)
    email = auth["email"]
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    err = _fail_until_locked(client, email)
    assert err["code"] == "account_locked" and err["reason"] == "too_many_failed_attempts"
    assert err["failed_attempts"] == 4
    assert 290 <= err["retry_after_seconds"] <= 300  # 5 minutos
    assert "locked_until" in err and "5 minutos" in err["message"]
    # Bloqueada: ni la contraseña correcta entra
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": PASSWORD})
    assert r.status_code == 423
    assert r.headers["retry-after"] == str(r.json()["error"]["retry_after_seconds"])

    # Al vencer el bloqueo, un nuevo error bloquea más tiempo (15 min)
    _expire_lock(db_ready)
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "Mala1234"})
    assert r.status_code == 423
    assert r.json()["error"]["failed_attempts"] == 5
    assert 890 <= r.json()["error"]["retry_after_seconds"] <= 900

    # Tras vencer, la contraseña correcta entra y limpia el historial
    _expire_lock(db_ready)
    assert client.post("/api/v2/auth/login", headers=BFF_HEADERS,
                       json={"email": email, "password": PASSWORD}).status_code == 200
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "Mala1234"})
    assert r.json()["error"]["attempts_left"] == 2


def test_unknown_email_gets_same_lock(client):
    # Mismas respuestas que una cuenta real: el bloqueo no revela si el email existe
    err = _fail_until_locked(client, f"nadie_{uuid.uuid4().hex[:8]}@example.com")
    assert err["code"] == "account_locked" and err["failed_attempts"] == 4


def test_lock_is_shared_with_delete_me(client, outbox):
    auth = _register(client, outbox)
    email, token = auth["email"], auth["tokens"]["access_token"]
    for _ in range(3):
        r = client.request("DELETE", "/api/v2/users/me", headers=_auth(token), json={"password": "Mala1234"})
        assert r.status_code == 401
    r = client.request("DELETE", "/api/v2/users/me", headers=_auth(token), json={"password": "Mala1234"})
    assert r.status_code == 423
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": PASSWORD})
    assert r.status_code == 423


def test_legacy_bcrypt_user_is_migrated_to_argon2(client, db_ready):
    email = f"legacy_{uuid.uuid4().hex[:8]}@example.com"
    legacy_hash = bcrypt.hashpw(b"Vieja123", bcrypt.gensalt()).decode()
    with psycopg.connect(db_ready) as conn:
        conn.execute(
            'INSERT INTO "user" (id, first_name, last_name, username, email, hashed_password, created_at, status) '
            "VALUES (gen_random_uuid(), 'L', 'U', %s, %s, %s, now(), true)",
            (f"legacy_{uuid.uuid4().hex[:6]}", email, legacy_hash),
        )
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "Vieja123"})
    assert r.status_code == 200
    assert r.json()["user"]["needs_consent"] is True  # usuario de v1 sin consentimiento registrado
    with psycopg.connect(db_ready) as conn:
        stored = conn.execute('SELECT hashed_password FROM "user" WHERE email = %s', (email,)).fetchone()[0]
    assert stored.startswith("$argon2id$")


def test_consent_clears_needs_consent(client, outbox, db_ready):
    auth = _register(client, outbox)
    token = auth["tokens"]["access_token"]
    r = client.post("/api/v2/users/me/consents", headers=_auth(token),
                    json={"terms_version": "viejo", "privacy_version": "viejo"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "legal_version_mismatch"
    r = client.post("/api/v2/users/me/consents", headers=_auth(token), json={
        "terms_version": settings.LEGAL_TERMS_VERSION, "privacy_version": settings.LEGAL_PRIVACY_VERSION})
    assert r.status_code == 204


def test_password_reset_revokes_sessions(client, outbox):
    auth = _register(client, outbox)
    email = auth["email"]
    time.sleep(1.1)  # iat del token anterior < password_changed_at
    r = client.post("/api/v2/auth/forgot-password", headers=BFF_HEADERS, json={"email": email})
    assert r.status_code == 200
    code = extract_code(outbox[-1])
    r = client.post("/api/v2/auth/reset-password", headers=BFF_HEADERS,
                    json={"email": email, "code": code, "new_password": "NuevaClave1234"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v2/users/me", headers=_auth(auth["tokens"]["access_token"])).status_code == 401
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": auth["tokens"]["refresh_token"]})
    assert r.status_code == 401
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "NuevaClave1234"})
    assert r.status_code == 200


def test_forgot_password_unknown_email_same_response(client, outbox):
    r = client.post("/api/v2/auth/forgot-password", headers=BFF_HEADERS, json={"email": "nadie@example.com"})
    assert r.status_code == 200
    assert outbox == []


def test_deactivate_and_reactivate(client, outbox):
    auth = _register(client, outbox)
    email, token = auth["email"], auth["tokens"]["access_token"]
    r = client.request("DELETE", "/api/v2/users/me", headers=_auth(token), json={"password": "Mala1234"})
    assert r.status_code == 401
    r = client.request("DELETE", "/api/v2/users/me", headers=_auth(token), json={"password": PASSWORD})
    assert r.status_code == 204
    # El access token y el refresh dejan de servir
    assert client.get("/api/v2/users/me", headers=_auth(token)).status_code == 401
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": auth["tokens"]["refresh_token"]})
    assert r.status_code == 401
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": PASSWORD})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "account_deactivated" and "reactivate_until" in err
    r = client.post("/api/v2/auth/reactivate", headers=BFF_HEADERS, json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    assert client.get("/api/v2/users/me", headers=_auth(r.json()["tokens"]["access_token"])).status_code == 200


def test_logout_all(client, outbox):
    auth = _register(client, outbox)
    r = client.post("/api/v2/auth/logout-all", headers=_auth(auth["tokens"]["access_token"]))
    assert r.status_code == 204
    r = client.post("/api/v2/auth/refresh", headers=BFF_HEADERS, json={"refresh_token": auth["tokens"]["refresh_token"]})
    assert r.status_code == 401


def _random_ip() -> str:
    return f"198.51.{uuid.uuid4().int % 250 + 1}.{uuid.uuid4().int % 250 + 1}"


def _random_email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def test_login_rate_limit_by_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setitem(rate_limit.RULES, "login", {"ip": (3, 600), "email": (100, 600)})
    headers = {**BFF_HEADERS, "X-Client-IP": _random_ip()}
    codes = [
        client.post("/api/v2/auth/login", headers=headers, json={"email": _random_email("rl"), "password": "x"}).status_code
        for _ in range(4)
    ]
    assert codes == [401, 401, 401, 429]
    r = client.post("/api/v2/auth/login", headers=headers, json={"email": _random_email("rl"), "password": "x"})
    err = r.json()["error"]
    assert err["code"] == "rate_limited" and err["retry_after_seconds"] > 0
    assert r.headers["retry-after"] == str(err["retry_after_seconds"])
    # Otra IP real (vía BFF) no está limitada
    other = {**BFF_HEADERS, "X-Client-IP": _random_ip()}
    r = client.post("/api/v2/auth/login", headers=other, json={"email": _random_email("rl"), "password": "x"})
    assert r.status_code == 401


def test_rate_limit_by_email_across_ips(client, monkeypatch, outbox):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setitem(rate_limit.RULES, "forgot", {"ip": (100, 3600), "email": (2, 3600)})
    email = _random_email("fp")
    codes = [
        client.post("/api/v2/auth/forgot-password", headers={**BFF_HEADERS, "X-Client-IP": _random_ip()},
                    json={"email": email.upper() if i % 2 else email}).status_code
        for i in range(3)
    ]
    assert codes == [200, 200, 429]


def test_signup_rejects_breached_password(client, outbox, monkeypatch):
    async def breached(password):
        return True

    monkeypatch.setattr(hibp, "is_breached", breached)
    r = client.post("/api/v2/auth/signup", headers=BFF_HEADERS,
                    json=_signup_payload(_random_email("b"), f"b_{uuid.uuid4().hex[:8]}"))
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "password_breached" and "password" in err["fields"]
    assert outbox == []


def test_reset_rejects_breached_password_without_spending_code(client, outbox, monkeypatch):
    auth = _register(client, outbox)
    email = auth["email"]
    client.post("/api/v2/auth/forgot-password", headers=BFF_HEADERS, json={"email": email})
    code = extract_code(outbox[-1])

    async def breached(password):
        return password == "Filtrada12345"

    monkeypatch.setattr(hibp, "is_breached", breached)
    r = client.post("/api/v2/auth/reset-password", headers=BFF_HEADERS,
                    json={"email": email, "code": code, "new_password": "Filtrada12345"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "password_breached"
    assert "new_password" in r.json()["error"]["fields"]
    # El mismo código sigue sirviendo con una contraseña segura
    r = client.post("/api/v2/auth/reset-password", headers=BFF_HEADERS,
                    json={"email": email, "code": code, "new_password": "NuevaClave1234"})
    assert r.status_code == 200


def test_reset_password_lifts_login_lock(client, outbox):
    auth = _register(client, outbox)
    email = auth["email"]
    _fail_until_locked(client, email)
    client.post("/api/v2/auth/forgot-password", headers=BFF_HEADERS, json={"email": email})
    code = extract_code(outbox[-1])
    r = client.post("/api/v2/auth/reset-password", headers=BFF_HEADERS,
                    json={"email": email, "code": code, "new_password": "NuevaClave1234"})
    assert r.status_code == 200
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS, json={"email": email, "password": "NuevaClave1234"})
    assert r.status_code == 200


def test_short_password_rejected(client):
    r = client.post("/api/v2/auth/signup", headers=BFF_HEADERS,
                    json=_signup_payload(_random_email("c"), f"c_{uuid.uuid4().hex[:8]}", password="Corta123456"))
    assert r.status_code == 422 and "password" in r.json()["error"]["fields"]
