"""Recomendaciones con TMDB simulado (Postgres desechable)."""
import asyncio
import uuid

import httpx
import pytest

from app.integrations import tmdb
from tests.test_api_v2_integration import _auth, _register

pytestmark = pytest.mark.usefixtures("db_ready")

ACTION, DRAMA, HORROR = 28, 18, 27


def _m(mid: int, genres: list, title: str = None) -> dict:
    return {"id": mid, "title": title or f"Peli {mid}", "poster_path": f"/{mid}.jpg",
            "release_date": "2010-05-01", "genre_ids": genres, "adult": False}


FAKE = {
    "/movie/550/recommendations": [_m(1, [DRAMA]), _m(2, [ACTION]), _m(3, [HORROR]), _m(13, [DRAMA])],
    "/movie/13/recommendations": [_m(1, [DRAMA]), _m(4, [DRAMA])],
    "/discover/movie?with_people=287": [_m(5, [ACTION]), _m(550, [DRAMA])],
    "/discover/movie?with_genres=18": [_m(6, [DRAMA]), {**_m(7, [DRAMA]), "adult": True}],
    "/genre/movie/list": None,
    "/trending/movie/week": [_m(100, [ACTION]), _m(101, [DRAMA])],
    "/movie/3": {"id": 3, "title": "Peli 3", "poster_path": "/3.jpg", "release_date": "2001-01-01",
                 "genres": [{"id": HORROR, "name": "Terror"}]},
}


@pytest.fixture
def fake_tmdb(monkeypatch):
    calls = []

    async def fake_get(client, path, params, ttl_seconds=None):
        calls.append(path)
        key = path
        if path == "/discover/movie":
            key += f"?with_people={params['with_people']}" if "with_people" in params else f"?with_genres={params['with_genres']}"
        if path == "/genre/movie/list":
            return {"genres": [{"id": DRAMA, "name": "Drama"}, {"id": ACTION, "name": "Acción"}]}
        data = FAKE.get(key)
        if data is None:
            return None
        return data if isinstance(data, dict) else {"results": data}

    monkeypatch.setattr(tmdb, "get", fake_get)
    return calls


@pytest.fixture
def user(client, outbox):
    auth = _register(client, outbox)
    auth["h"] = _auth(auth["tokens"]["access_token"])
    return auth


def test_new_user_gets_popular(client, user, fake_tmdb):
    r = client.get("/api/v2/recommendations", headers=user["h"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["movie_id"] for i in items] == ["100", "101"]
    assert items[0]["reasons"] == [{"type": "popular"}]


def test_hybrid_scoring_reasons_and_exclusions(client, user, fake_tmdb):
    h = user["h"]
    client.post("/api/v2/favorites", headers=h, json={"movie_id": "550", "title": "Fight Club"})
    client.post("/api/v2/reviews", headers=h, json={"movie_id": "13", "movie_title": "Forrest Gump", "rating": 5, "content": "Top"})
    client.post("/api/v2/favorites/people", headers=h, json={"person_id": "287", "name": "Brad Pitt"})
    client.patch("/api/v2/users/me", headers=h, json={"favorite_genres": [DRAMA]})
    client.post("/api/v2/lists/watchlist", headers=h, json={"movie_id": "2", "title": "Peli 2"})

    page = client.get("/api/v2/recommendations", headers=h).json()
    ids = [i["movie_id"] for i in page["items"]]
    # Excluidas: favoritas (550), reseñadas (13), en watchlist (2) y adultas (7)
    assert not {"550", "13", "2", "7"} & set(ids)
    # La 1 la recomiendan dos fuentes + bonus de género: queda primera
    assert ids[0] == "1" and page["items"][0]["score"] == 1.0
    reason_types = {r["type"] for r in page["items"][0]["reasons"]}
    assert reason_types <= {"because_liked", "because_rated", "genre_match"}
    person = next(i for i in page["items"] if i["movie_id"] == "5")
    assert person["reasons"][0] == {"type": "because_person", "person_id": "287", "name": "Brad Pitt"}
    genre = next(i for i in page["items"] if i["movie_id"] == "6")
    assert {"type": "genre_match", "genre_id": DRAMA, "genre_name": "Drama"} in genre["reasons"]


def test_dismiss_excludes_and_penalizes_genre(client, user, fake_tmdb):
    h = user["h"]
    client.post("/api/v2/favorites", headers=h, json={"movie_id": "550", "title": "Fight Club"})
    assert "3" in [i["movie_id"] for i in client.get("/api/v2/recommendations", headers=h).json()["items"]]

    assert client.post("/api/v2/recommendations/dismiss", headers=h, json={"movie_id": "3"}).status_code == 204
    assert "3" not in [i["movie_id"] for i in client.get("/api/v2/recommendations", headers=h).json()["items"]]
    assert client.get("/api/v2/movies/3/state", headers=h).json()["dismissed"] is True

    assert client.delete("/api/v2/recommendations/dismiss/3", headers=h).status_code == 204
    assert client.get("/api/v2/movies/3/state", headers=h).json()["dismissed"] is False


def test_dismiss_already_seen_marks_watched(client, user, fake_tmdb):
    h = user["h"]
    r = client.post("/api/v2/recommendations/dismiss", headers=h, json={"movie_id": "3", "reason": "already_seen"})
    assert r.status_code == 204
    watched = client.get("/api/v2/lists/watched", headers=h).json()["items"]
    assert [(w["movie_id"], w["title"]) for w in watched] == [("3", "Peli 3")]


def test_pagination(client, user, fake_tmdb):
    h = user["h"]
    client.post("/api/v2/favorites", headers=h, json={"movie_id": "550", "title": "Fight Club"})
    first = client.get("/api/v2/recommendations", headers=h, params={"limit": 2}).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = client.get("/api/v2/recommendations", headers=h, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert not {i["movie_id"] for i in first["items"]} & {i["movie_id"] for i in second["items"]}


def test_tmdb_client_uses_db_cache(db_ready):
    hits = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request)
        assert request.headers["authorization"] == "Bearer tmdb-test-token"
        return httpx.Response(200, json={"results": [{"id": 1}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            params = {"language": "es-ES", "nonce": uuid.uuid4().hex}
            a = await tmdb.get(client, "/movie/1/recommendations", params)
            b = await tmdb.get(client, "/movie/1/recommendations", params)
            return a, b

    a, b = asyncio.run(run())
    assert a == b == {"results": [{"id": 1}]}
    assert len(hits) == 1  # la segunda vino de la caché


def test_tmdb_failure_does_not_break(db_ready):
    def handler(request):
        return httpx.Response(500)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await tmdb.get(client, "/movie/1", {"nonce": uuid.uuid4().hex})

    assert asyncio.run(run()) is None
