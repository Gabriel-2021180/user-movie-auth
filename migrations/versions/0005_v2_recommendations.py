"""v2 recomendaciones: caché de TMDB, descartes y señales del usuario.

Revision ID: 0005_v2_recommendations
Revises: 0004_v2_legal
Create Date: 2026-10-03
"""
from alembic import op

from migrations.sql_runner import run_sql_file

revision = "0005_v2_recommendations"
down_revision = "0004_v2_legal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0005_v2_recommendations.sql")


def downgrade() -> None:
    # Destructivo: borra los descartes. No correr en producción sin respaldo.
    for fn in ("tmdb_cache_get(text)", "tmdb_cache_put(text, jsonb, integer)",
               "dismiss_add(uuid, text, text, integer[])", "dismiss_remove(uuid, text)", "reco_signals(uuid)"):
        op.execute(f"DROP FUNCTION IF EXISTS api.{fn}")
    op.execute("DROP TABLE IF EXISTS recommendation_dismissal, tmdb_cache")
