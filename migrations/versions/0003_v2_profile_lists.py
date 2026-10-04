"""v2 perfil, onboarding, listas y funciones para favoritos, personas y reseñas.

Revision ID: 0003_v2_profile_lists
Revises: 0002_v2_auth
Create Date: 2026-10-03
"""
from alembic import op

from migrations.sql_runner import run_sql_file

revision = "0003_v2_profile_lists"
down_revision = "0002_v2_auth"
branch_labels = None
depends_on = None

_FUNCTIONS = [
    "user_public(text)",
    "user_update_profile(uuid, text, text, text, boolean, text, text, integer[])",
    "onboarding_complete(uuid, integer[], jsonb, jsonb)",
    "favorite_list(uuid, timestamptz, text, integer)",
    "favorite_add(uuid, text, text, text, text)",
    "favorite_remove(uuid, text)",
    "favorite_person_list(uuid, timestamptz, text, integer)",
    "favorite_person_add(uuid, text, text, text, text, text)",
    "favorite_person_remove(uuid, text)",
    "watchlist_list(uuid, timestamptz, text, integer)",
    "watchlist_add(uuid, text, text, text, text)",
    "watchlist_remove(uuid, text)",
    "watched_list(uuid, timestamptz, text, integer)",
    "watched_add(uuid, text, text, text, text, timestamptz)",
    "watched_remove(uuid, text)",
    "list_all(uuid)",
    "list_get(uuid, uuid)",
    "list_create(uuid, text, text, boolean, integer)",
    "list_update(uuid, uuid, text, boolean, text, boolean)",
    "list_delete(uuid, uuid)",
    "list_items(uuid, timestamptz, text, integer)",
    "list_item_add(uuid, uuid, text, text, text, text, integer)",
    "list_item_remove(uuid, uuid, text)",
    "review_list_by_movie(text, timestamptz, text, integer)",
    "review_movie_summary(text)",
    "review_list_by_user(uuid, timestamptz, text, integer)",
    "review_get(uuid)",
    "_sentiment(integer)",
    "review_create(uuid, text, text, text, text, integer, text)",
    "review_update(uuid, uuid, integer, text)",
    "review_delete(uuid, uuid)",
    "movie_state(uuid, text)",
]


def upgrade() -> None:
    run_sql_file("0003_v2_profile_lists.sql")


def downgrade() -> None:
    # Destructivo: borra listas, vistas, "ver después" y semillas. No correr en producción sin respaldo.
    for fn in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS api.{fn}")
    op.execute("DROP TABLE IF EXISTS user_list_item, user_list, watchlist_item, watched_item, user_seed_movie")
    op.execute("DROP INDEX IF EXISTS favoriteperson_user_idx")
    # api.user_me vuelve a la versión de 0002
    op.execute("DROP FUNCTION IF EXISTS api.user_me(uuid)")
    from pathlib import Path
    sql = (Path(__file__).parent.parent / "sql" / "0002_v2_auth.sql").read_text(encoding="utf-8")
    start = sql.index("CREATE OR REPLACE FUNCTION api.user_me")
    end = sql.index("$$;", sql.index("$$", start) + 2) + 3
    op.execute(sql[start:end])
