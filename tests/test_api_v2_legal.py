"""Exportación de datos y purga diaria (Postgres desechable)."""
import random

import psycopg
import pytest

from tests.conftest import BFF_HEADERS
from tests.test_api_v2_integration import PASSWORD, _auth, _register

pytestmark = pytest.mark.usefixtures("db_ready")

CRON = {"Authorization": "Bearer cron-test-secret"}


def test_export_contains_my_data_without_secrets(client, outbox):
    auth = _register(client, outbox)
    h = _auth(auth["tokens"]["access_token"])
    client.post("/api/v2/favorites", headers=h, json={"movie_id": "550", "title": "Fight Club"})
    client.post("/api/v2/reviews", headers=h, json={"movie_id": "550", "movie_title": "Fight Club", "rating": 5, "content": "Top"})
    r = client.get("/api/v2/users/me/export", headers=h)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["email"] == auth["email"]
    assert [f["movie_id"] for f in data["favorites"]] == ["550"]
    assert len(data["reviews"]) == 1 and len(data["consents"]) == 1 and len(data["sessions"]) == 1
    assert "hashed_password" not in r.text and "token_hash" not in r.text and "exported_at" in data


def test_cron_requires_secret(client):
    assert client.get("/api/internal/cron/purge").status_code == 404
    assert client.get("/api/internal/cron/purge", headers={"Authorization": "Bearer mal"}).status_code == 404


def test_purge_deletes_expired_accounts_and_anonymizes_reviews(client, outbox, db_ready):
    auth = _register(client, outbox)
    h = _auth(auth["tokens"]["access_token"])
    uid = auth["user"]["id"]
    mid = str(random.randint(10_000_000, 99_999_999))  # película única: la BD de test se reutiliza
    client.post("/api/v2/favorites", headers=h, json={"movie_id": mid, "title": "X"})
    client.post("/api/v2/lists", headers=h, json={"name": "Mi lista"})
    client.post("/api/v2/reviews", headers=h, json={"movie_id": mid, "movie_title": "X", "rating": 4, "content": "Bien"})
    assert client.request("DELETE", "/api/v2/users/me", headers=h, json={"password": PASSWORD}).status_code == 204

    # Dentro del plazo de gracia no se purga
    client.get("/api/internal/cron/purge", headers=CRON)
    with psycopg.connect(db_ready) as conn:
        assert conn.execute('SELECT count(*) FROM "user" WHERE id = %s', (uid,)).fetchone()[0] == 1
        conn.execute("UPDATE \"user\" SET deactivated_at = now() - interval '91 days' WHERE id = %s", (uid,))

    r = client.get("/api/internal/cron/purge", headers=CRON)
    assert r.status_code == 200 and r.json()["users_purged"] >= 1

    with psycopg.connect(db_ready) as conn:
        assert conn.execute('SELECT count(*) FROM "user" WHERE id = %s', (uid,)).fetchone()[0] == 0
        for table in ("favorite", "user_list", "refresh_token", "user_consent"):
            assert conn.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s", (uid,)).fetchone()[0] == 0
    page = client.get(f"/api/v2/reviews/movie/{mid}", headers=BFF_HEADERS).json()
    assert page["items"][0]["username"] == "Usuario eliminado" and page["items"][0]["user_id"] is None
    assert page["summary"]["count"] == 1
    # Ya no puede reactivar
    r = client.post("/api/v2/auth/reactivate", headers=BFF_HEADERS, json={"email": auth["email"], "password": PASSWORD})
    assert r.status_code == 401


def test_session_retention(client, outbox, db_ready):
    auth = _register(client, outbox)
    uid = auth["user"]["id"]
    with psycopg.connect(db_ready) as conn:
        conn.execute(
            "INSERT INTO refresh_token (user_id, family_id, token_hash, created_at, expires_at, revoked_at) "
            "VALUES (%s, gen_random_uuid(), %s, now() - interval '200 days', now() - interval '150 days', now() - interval '100 days')",
            (uid, b"old-token-hash-0001"),
        )
    client.get("/api/internal/cron/purge", headers=CRON)
    with psycopg.connect(db_ready) as conn:
        hashes = [r[0] for r in conn.execute("SELECT token_hash FROM refresh_token WHERE user_id = %s", (uid,))]
    assert b"old-token-hash-0001" not in [bytes(h) for h in hashes]
    assert len(hashes) == 1  # la sesión vigente se conserva
