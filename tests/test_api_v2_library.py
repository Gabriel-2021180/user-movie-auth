"""Perfil, onboarding, favoritos, listas y reseñas de v2 (Postgres desechable)."""
import uuid

import psycopg
import pytest

from tests.conftest import BFF_HEADERS
from tests.test_api_v2_integration import PASSWORD, _auth, _register

pytestmark = pytest.mark.usefixtures("db_ready")


def _movie(mid: str, title: str = "Peli") -> dict:
    return {"movie_id": mid, "title": title, "poster": f"/p{mid}.jpg", "year": "1999"}


@pytest.fixture
def user(client, outbox):
    auth = _register(client, outbox)
    auth["h"] = _auth(auth["tokens"]["access_token"])
    return auth


def test_profile_patch_rules(client, user, db_ready):
    h = user["h"]
    r = client.patch("/api/v2/users/me", headers=h, json={"bio": "Cinéfilo", "favorite_genres": [28, 18, 28]})
    assert r.status_code == 200, r.text
    assert r.json()["bio"] == "Cinéfilo" and r.json()["favorite_genres"] == [28, 18]

    # bio null la borra; no enviar bio no la cambia
    assert client.patch("/api/v2/users/me", headers=h, json={"banner_color": "#112233"}).json()["bio"] == "Cinéfilo"
    assert client.patch("/api/v2/users/me", headers=h, json={"bio": None}).json()["bio"] is None

    # Color: 3 cambios por día (ya hubo 1)
    for color in ["#000001", "#000002"]:
        assert client.patch("/api/v2/users/me", headers=h, json={"banner_color": color}).status_code == 200
    r = client.patch("/api/v2/users/me", headers=h, json={"banner_color": "#000003"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "color_change_limit"

    # Nombre: una vez cada 14 días
    assert client.patch("/api/v2/users/me", headers=h, json={"first_name": "Nueva"}).status_code == 200
    r = client.patch("/api/v2/users/me", headers=h, json={"last_name": "Otra"})
    assert r.status_code == 429 and r.json()["error"]["days_left"] == 14
    # Enviar el mismo valor no cuenta como cambio
    assert client.patch("/api/v2/users/me", headers=h, json={"first_name": "Nueva"}).status_code == 200

    r = client.patch("/api/v2/users/me", headers=h, json={"banner_color": "rojo"})
    assert r.status_code == 422


def test_public_profile_hides_deactivated(client, user):
    username = user["user"]["username"]
    r = client.get(f"/api/v2/users/{username.upper()}", headers=BFF_HEADERS)
    assert r.status_code == 200
    assert set(r.json()) == {"username", "avatar_url", "bio", "banner_color", "created_at", "stats"}
    client.request("DELETE", "/api/v2/users/me", headers=user["h"], json={"password": PASSWORD})
    assert client.get(f"/api/v2/users/{username}", headers=BFF_HEADERS).status_code == 404


def test_onboarding(client, user):
    h = user["h"]
    r = client.put("/api/v2/onboarding", headers=h, json={"genres": [28], "seed_movies": [_movie("1")]})
    assert r.status_code == 422
    r = client.put("/api/v2/onboarding", headers=h, json={
        "genres": [28, 12, 878],
        "seed_movies": [_movie("603"), _movie("550"), _movie("13")],
        "seed_people": [{"person_id": "287", "name": "Brad Pitt"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["onboarding_completed"] is True and r.json()["favorite_genres"] == [28, 12, 878]
    people = client.get("/api/v2/favorites/people", headers=h).json()["items"]
    assert [p["person_id"] for p in people] == ["287"]


def test_favorites_idempotent_and_paginated(client, user):
    h = user["h"]
    r = client.post("/api/v2/favorites", headers=h, json=_movie("550", "Fight Club"))
    assert r.status_code == 201
    assert client.post("/api/v2/favorites", headers=h, json=_movie("550", "Fight Club")).status_code == 200
    for mid in ["1", "2", "3", "4"]:
        client.post("/api/v2/favorites", headers=h, json=_movie(mid))

    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get("/api/v2/favorites", headers=h, params=params).json()
        seen += [i["movie_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert sorted(seen) == ["1", "2", "3", "4", "550"] and len(seen) == len(set(seen))

    assert client.delete("/api/v2/favorites/550", headers=h).status_code == 204
    assert client.get("/api/v2/users/me", headers=h).json()["stats"]["favorites"] == 4
    r = client.get("/api/v2/favorites", headers=h, params={"cursor": "basura"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_cursor"


def test_poster_must_be_safe(client, user):
    r = client.post("/api/v2/favorites", headers=user["h"],
                    json={"movie_id": "1", "title": "x", "poster": "javascript:alert(1)"})
    assert r.status_code == 422


def test_watchlist_and_watched(client, user):
    h = user["h"]
    assert client.post("/api/v2/lists/watchlist", headers=h, json=_movie("10")).status_code == 201
    assert client.post("/api/v2/lists/watchlist", headers=h, json=_movie("10")).status_code == 200
    r = client.post("/api/v2/lists/watched", headers=h, json={**_movie("10"), "watched_at": "2026-09-01T20:00:00Z"})
    assert r.status_code == 201 and r.json()["watched_at"].startswith("2026-09-01")
    # Al marcarla vista sale de "ver después"
    assert client.get("/api/v2/lists/watchlist", headers=h).json()["items"] == []
    stats = client.get("/api/v2/users/me", headers=h).json()["stats"]
    assert stats["watched"] == 1 and stats["watchlist"] == 0
    r = client.post("/api/v2/lists/watched", headers=h, json={**_movie("11"), "watched_at": "2999-01-01T00:00:00Z"})
    assert r.status_code == 422


def test_custom_lists(client, user, outbox):
    h = user["h"]
    r = client.post("/api/v2/lists", headers=h, json={"name": "Clásicos", "description": "Los de siempre"})
    assert r.status_code == 201
    list_id = r.json()["id"]
    assert client.post("/api/v2/lists", headers=h, json={"name": "clásicos"}).json()["error"]["code"] == "list_name_taken"

    assert client.post(f"/api/v2/lists/{list_id}/items", headers=h, json=_movie("100")).status_code == 201
    assert client.post(f"/api/v2/lists/{list_id}/items", headers=h, json=_movie("100")).status_code == 200
    detail = client.get(f"/api/v2/lists/{list_id}", headers=h).json()
    assert detail["item_count"] == 1 and detail["is_owner"] and detail["items"][0]["movie_id"] == "100"

    # Otro usuario no ve la lista privada, ni puede modificarla
    other = _register(client, outbox)
    oh = _auth(other["tokens"]["access_token"])
    assert client.get(f"/api/v2/lists/{list_id}", headers=oh).status_code == 404
    assert client.post(f"/api/v2/lists/{list_id}/items", headers=oh, json=_movie("5")).status_code == 404
    assert client.delete(f"/api/v2/lists/{list_id}", headers=oh).status_code == 404

    # Pública: la ve pero no es dueño
    r = client.patch(f"/api/v2/lists/{list_id}", headers=h, json={"is_public": True, "description": None})
    assert r.status_code == 200 and r.json()["description"] is None
    seen = client.get(f"/api/v2/lists/{list_id}", headers=oh).json()
    assert seen["is_owner"] is False and seen["owner_username"] == user["user"]["username"]

    state = client.get("/api/v2/movies/100/state", headers=h).json()
    assert state["in_lists"] == [list_id]

    assert client.delete(f"/api/v2/lists/{list_id}/items/100", headers=h).status_code == 204
    assert client.delete(f"/api/v2/lists/{list_id}", headers=h).status_code == 204
    assert client.get("/api/v2/lists", headers=h).json() == []


def test_reviews(client, user, outbox):
    h = user["h"]
    body = {"movie_id": "27205", "movie_title": "Inception", "movie_poster": "/i.jpg", "rating": 5, "content": "Genial"}
    r = client.post("/api/v2/reviews", headers=h, json=body)
    assert r.status_code == 201, r.text
    review = r.json()
    assert review["sentiment"] == "positive" and review["username"] == user["user"]["username"]
    assert client.post("/api/v2/reviews", headers=h, json=body).json()["error"]["code"] == "review_exists"

    r = client.put(f"/api/v2/reviews/{review['id']}", headers=h, json={"rating": 2})
    assert r.json()["sentiment"] == "negative" and r.json()["content"] == "Genial"

    other = _register(client, outbox)
    oh = _auth(other["tokens"]["access_token"])
    assert client.put(f"/api/v2/reviews/{review['id']}", headers=oh, json={"rating": 5}).status_code == 403
    assert client.delete(f"/api/v2/reviews/{review['id']}", headers=oh).status_code == 403

    page = client.get("/api/v2/reviews/movie/27205", headers=BFF_HEADERS).json()
    assert page["summary"] == {"count": 1, "avg_rating": 2.0}
    assert client.get("/api/v2/movies/27205/state", headers=h).json()["my_review"]["id"] == review["id"]
    assert len(client.get("/api/v2/reviews/me", headers=h).json()["items"]) == 1

    # Las reseñas de cuentas dadas de baja no se muestran
    client.request("DELETE", "/api/v2/users/me", headers=h, json={"password": PASSWORD})
    page = client.get("/api/v2/reviews/movie/27205", headers=BFF_HEADERS).json()
    assert page["items"] == [] and page["summary"]["count"] == 0


def test_review_delete(client, user):
    h = user["h"]
    body = {"movie_id": "1", "movie_title": "X", "rating": 3, "content": "Ok"}
    rid = client.post("/api/v2/reviews", headers=h, json=body).json()["id"]
    assert client.delete(f"/api/v2/reviews/{rid}", headers=h).status_code == 204
    assert client.delete(f"/api/v2/reviews/{rid}", headers=h).status_code == 404


def test_v1_and_v2_share_favorites(client, user, db_ready):
    """Lo que el usuario guardó con v1 aparece en v2 (misma tabla)."""
    with psycopg.connect(db_ready) as conn:
        conn.execute(
            "INSERT INTO favorite (id, user_id, movie_id, title, added_at, status) VALUES (%s, %s, '42', 'De v1', now(), true)",
            (uuid.uuid4(), user["user"]["id"]),
        )
    items = client.get("/api/v2/favorites", headers=user["h"]).json()["items"]
    assert [i["movie_id"] for i in items] == ["42"]
