import uuid
from datetime import timedelta

import bcrypt
import jwt
import pytest
from starlette.requests import Request

from app.core import security
from app.core.client_ip import get_client_ip


def test_argon2_hash_and_verify():
    h = security.get_password_hash("Secreta123")
    assert h.startswith("$argon2id$")
    assert security.verify_password("Secreta123", h)
    assert not security.verify_password("otra", h)
    assert not security.password_needs_rehash(h)


def test_legacy_bcrypt_hash_is_verified_and_flagged_for_rehash():
    legacy = bcrypt.hashpw(b"Vieja123", bcrypt.gensalt()).decode()
    assert security.verify_password("Vieja123", legacy)
    assert not security.verify_password("x", legacy)
    assert not security.verify_password("a" * 100, legacy)  # >72 bytes no revienta
    assert security.password_needs_rehash(legacy)


def test_access_token_roundtrip():
    uid = uuid.uuid4()
    claims = security.decode_access_token_v2(security.create_access_token_v2(uid))
    assert claims["sub"] == str(uid) and claims["type"] == "access"


def test_v1_token_is_rejected_by_v2():
    v1 = security.create_access_token({"sub": str(uuid.uuid4())}, timedelta(minutes=5))
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token_v2(v1)


def test_code_hash_depends_on_purpose_and_email():
    a = security.hash_code("signup", "A@x.com", "123456")
    assert a == security.hash_code("signup", "a@x.com", "123456")
    assert a != security.hash_code("password_reset", "a@x.com", "123456")
    assert len(security.generate_numeric_code()) == 6


def _request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1234)})


def test_client_ip_only_trusted_with_bff_secret():
    assert get_client_ip(_request({"X-Client-IP": "1.2.3.4"})) == "10.0.0.1"
    assert get_client_ip(_request({"X-Client-IP": "1.2.3.4", "X-BFF-Secret": "wrong"})) == "10.0.0.1"
    assert get_client_ip(_request({"X-Client-IP": "1.2.3.4", "X-BFF-Secret": "bff-test-secret"})) == "1.2.3.4"
    assert get_client_ip(_request({"X-Client-IP": "nope", "X-BFF-Secret": "bff-test-secret"})) == "10.0.0.1"
