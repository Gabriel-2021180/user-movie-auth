import asyncio
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.errors import APIError
from app.db import procedures
from app.db.pagination import decode_offset_cursor, encode_offset_cursor
from app.integrations import tmdb
from app.repositories import library_repository
from app.schemas.v2.recommendation import RecommendationItem, RecommendationPage

# Recomendación híbrida:
#  1) Fuentes: favoritos (1.0), reseñas 4-5★ (0.5-1.0), semillas del onboarding (0.8),
#     vistas (0.3) -> /movie/{id}/recommendations de TMDB.
#  2) Personas favoritas (0.4) -> /discover?with_people. Géneros favoritos (0.2) -> /discover?with_genres.
#  3) Bonus por géneros favoritos, castigo por géneros de lo descartado.
#  4) Se excluye lo ya visto, favorito, reseñado, en "ver después" o descartado.
# Cada ítem trae hasta 2 "reasons" (las que más aportaron).

MAX_SOURCE_MOVIES = 8
MAX_PEOPLE = 4
MAX_GENRES = 3
MAX_RESULTS = 100
W_PERSON, W_GENRE = 0.4, 0.2
GENRE_BONUS, GENRE_BONUS_CAP = 0.1, 0.3
DISMISS_PENALTY, DISMISS_PENALTY_CAP = 0.05, 0.3


def _rank_factor(rank: int) -> float:
    return 1.0 - rank / 40.0  # posición 0 -> 1.0, posición 19 -> 0.525


def _year(release_date: Optional[str]) -> Optional[str]:
    return release_date[:4] if release_date and len(release_date) >= 4 else None


def _sources(signals: dict) -> List[Tuple[str, float, dict]]:
    """Películas que el usuario valoró, con su peso y la razón que generan."""
    best: Dict[str, Tuple[float, dict]] = {}

    def add(movie_id: str, weight: float, reason: dict) -> None:
        if movie_id not in best or best[movie_id][0] < weight:
            best[movie_id] = (weight, reason)

    for r in signals["reviews"]:
        if r["rating"] >= 4:
            add(r["movie_id"], (r["rating"] - 3) / 2,
                {"type": "because_rated", "movie_id": r["movie_id"], "title": r["title"], "rating": r["rating"]})
    for f in signals["favorites"]:
        add(f["movie_id"], 1.0, {"type": "because_liked", "movie_id": f["movie_id"], "title": f["title"]})
    for s in signals["seeds"]:
        add(s["movie_id"], 0.8, {"type": "onboarding_seed", "movie_id": s["movie_id"], "title": s["title"]})
    for w in signals["watched"]:
        add(w["movie_id"], 0.3, {"type": "because_watched", "movie_id": w["movie_id"], "title": w["title"]})

    # Python mantiene el orden de inserción: a igual peso, la más reciente primero
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[:MAX_SOURCE_MOVIES]
    return [(mid, w, reason) for mid, (w, reason) in ranked]


async def _gather_candidates(signals: dict, language: str) -> Tuple[Dict[str, dict], Dict[str, Dict[str, Tuple[float, dict]]], Dict[int, str]]:
    sources = _sources(signals)
    people = signals["people"][:MAX_PEOPLE]
    genres = (signals["genres"] or [])[:MAX_GENRES]

    async with tmdb.new_client() as client:
        tasks = [tmdb.get(client, f"/movie/{mid}/recommendations", {"language": language, "page": 1})
                 for mid, _, _ in sources]
        tasks += [tmdb.get(client, "/discover/movie", {
            "language": language, "with_people": p["person_id"], "sort_by": "popularity.desc",
            "vote_count.gte": 50, "include_adult": "false"}) for p in people]
        tasks += [tmdb.get(client, "/discover/movie", {
            "language": language, "with_genres": g, "sort_by": "popularity.desc",
            "vote_average.gte": 6.5, "vote_count.gte": 300, "include_adult": "false"}) for g in genres]
        genre_task = tmdb.get(client, "/genre/movie/list", {"language": language}, settings.TMDB_GENRES_TTL_SECONDS)
        results = await asyncio.gather(*tasks, genre_task)

    genre_names = {g["id"]: g["name"] for g in (results[-1] or {}).get("genres", [])}
    responses = results[:-1]

    movies: Dict[str, dict] = {}
    contributions: Dict[str, Dict[str, Tuple[float, dict]]] = defaultdict(dict)

    def collect(response: Optional[dict], weight: float, reason: dict) -> None:
        for rank, m in enumerate((response or {}).get("results", [])[:20]):
            if m.get("adult") or m.get("softcore"):
                continue
            mid = str(m["id"])
            movies.setdefault(mid, m)
            key = f'{reason["type"]}:{reason.get("movie_id") or reason.get("person_id") or reason.get("genre_id")}'
            value = weight * _rank_factor(rank)
            if key not in contributions[mid] or contributions[mid][key][0] < value:
                contributions[mid][key] = (value, reason)

    i = 0
    for _, weight, reason in sources:
        collect(responses[i], weight, reason)
        i += 1
    for p in people:
        collect(responses[i], W_PERSON, {"type": "because_person", "person_id": p["person_id"], "name": p["name"]})
        i += 1
    for g in genres:
        collect(responses[i], W_GENRE, {"type": "genre_match", "genre_id": g, "genre_name": genre_names.get(g, str(g))})
        i += 1
    return movies, contributions, genre_names


async def _popular_fallback(language: str) -> Tuple[Dict[str, dict], Dict[str, Dict[str, Tuple[float, dict]]]]:
    async with tmdb.new_client() as client:
        data = await tmdb.get(client, "/trending/movie/week", {"language": language})
    movies, contributions = {}, defaultdict(dict)
    for rank, m in enumerate((data or {}).get("results", [])[:20]):
        if m.get("adult"):
            continue
        mid = str(m["id"])
        movies[mid] = m
        contributions[mid]["popular"] = (_rank_factor(rank), {"type": "popular"})
    return movies, contributions


async def compute(user_id: uuid.UUID, lang: str) -> List[RecommendationItem]:
    language = tmdb.LANGUAGES.get(lang, tmdb.LANGUAGES["es"])
    signals = await asyncio.to_thread(procedures.call_scalar, "api.reco_signals", p_user_id=user_id)
    if signals is None:
        raise APIError(404, "user_not_found", "Usuario no encontrado")

    movies, contributions, genre_names = await _gather_candidates(signals, language)

    excluded = {f["movie_id"] for f in signals["favorites"]} | {s["movie_id"] for s in signals["seeds"]}
    excluded |= {r["movie_id"] for r in signals["reviews"]} | {w["movie_id"] for w in signals["watched"]}
    excluded |= set(signals["watchlist"]) | {d["movie_id"] for d in signals["dismissed"]}

    if not any(mid not in excluded for mid in movies):
        movies, contributions = await _popular_fallback(language)

    favorite_genres = set(signals["genres"] or [])
    # Solo "no me interesa" castiga géneros; "ya la vi" solo la excluye
    dismissed_genres = Counter(
        g for d in signals["dismissed"] if d["reason"] == "not_interested" for g in d["genre_ids"]
    )

    scored = []
    for mid, m in movies.items():
        if mid in excluded:
            continue
        parts = dict(contributions[mid])
        movie_genres = m.get("genre_ids") or []
        matches = [g for g in movie_genres if g in favorite_genres]
        if matches:
            bonus = min(GENRE_BONUS * len(matches), GENRE_BONUS_CAP)
            key = f"genre_match:{matches[0]}"
            if key not in parts:
                parts[key] = (bonus, {"type": "genre_match", "genre_id": matches[0],
                                      "genre_name": genre_names.get(matches[0], str(matches[0]))})
            else:
                parts[key] = (parts[key][0] + bonus, parts[key][1])
        penalty = min(sum(dismissed_genres[g] for g in movie_genres) * DISMISS_PENALTY, DISMISS_PENALTY_CAP)
        score = sum(v for v, _ in parts.values()) - penalty
        if score <= 0:
            continue
        reasons = [r for _, r in sorted(parts.values(), key=lambda vr: -vr[0])[:2]]
        scored.append((score, mid, m, reasons))

    scored.sort(key=lambda t: (-t[0], t[1]))
    scored = scored[:MAX_RESULTS]
    top = scored[0][0] if scored else 1.0
    return [
        RecommendationItem(
            movie_id=mid, title=m.get("title") or m.get("original_title") or "", poster=m.get("poster_path"),
            year=_year(m.get("release_date")), score=round(score / top, 3), reasons=reasons,
        )
        for score, mid, m, reasons in scored
    ]


async def page(user_id: uuid.UUID, lang: str, cursor: Optional[str], limit: int) -> RecommendationPage:
    offset = decode_offset_cursor(cursor)
    items = await compute(user_id, lang)
    chunk = items[offset:offset + limit]
    nxt = encode_offset_cursor(offset + limit) if offset + limit < len(items) else None
    return RecommendationPage(items=chunk, next_cursor=nxt, generated_at=datetime.now(timezone.utc))


async def dismiss(user_id: uuid.UUID, movie_id: str, reason: str) -> None:
    async with tmdb.new_client() as client:
        details = await tmdb.get(client, f"/movie/{movie_id}", {"language": "es-ES"})
    genre_ids = [g["id"] for g in (details or {}).get("genres", [])]
    await asyncio.to_thread(
        procedures.call, "api.dismiss_add", p_user_id=user_id, p_movie_id=movie_id, p_reason=reason, p_genre_ids=genre_ids
    )
    if reason == "already_seen" and details and details.get("title"):
        await asyncio.to_thread(
            library_repository.watched_add, user_id, movie_id, details.get("title") or "",
            details.get("poster_path"), _year(details.get("release_date")), None,
        )


def undismiss(user_id: uuid.UUID, movie_id: str) -> None:
    procedures.call("api.dismiss_remove", p_user_id=user_id, p_movie_id=movie_id)
