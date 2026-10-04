"""v2 legal: exportación de datos, purga diaria y reseñas anonimizables.

Revision ID: 0004_v2_legal
Revises: 0003_v2_profile_lists
Create Date: 2026-10-03
"""
from alembic import op

from migrations.sql_runner import run_sql_file

revision = "0004_v2_legal"
down_revision = "0003_v2_profile_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0004_v2_legal.sql")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS api.purge_run(integer, integer)")
    op.execute("DROP FUNCTION IF EXISTS api.user_export(uuid)")
    # Falla si ya hay reseñas anonimizadas (user_id NULL): es intencional, no se pierden datos
    op.execute("ALTER TABLE review ALTER COLUMN user_id SET NOT NULL")
