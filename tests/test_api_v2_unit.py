from tests.conftest import BFF_HEADERS


def test_v2_requires_bff_secret(client):
    r = client.get("/api/v2/legal/current")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "bff_required", "message": "Origen no autorizado"}}


def test_legal_current(client):
    r = client.get("/api/v2/legal/current", headers=BFF_HEADERS)
    assert r.status_code == 200
    assert set(r.json()) == {"terms_version", "privacy_version", "terms_url", "privacy_url"}
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_validation_error_envelope(client):
    r = client.post("/api/v2/auth/signup", headers=BFF_HEADERS, json={
        "email": "no-es-email", "username": "a", "first_name": "A", "last_name": "B",
        "password": "corta", "accepted_terms_version": "x", "accepted_privacy_version": "y",
    })
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert {"email", "username", "password"} <= set(err["fields"])


def test_unknown_fields_rejected(client):
    r = client.post("/api/v2/auth/login", headers=BFF_HEADERS,
                    json={"email": "a@b.com", "password": "x", "is_admin": True})
    assert r.status_code == 422


def test_me_without_token(client):
    r = client.get("/api/v2/users/me", headers=BFF_HEADERS)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_token"


def test_v1_errors_keep_old_format(client):
    r = client.get("/api/v1/favorites/")
    assert r.status_code == 401
    assert "detail" in r.json()


def test_docs_hidden_outside_development(client):
    assert client.get("/docs").status_code == 404
