"""v2 seguridad de auth: límite de solicitudes en BD y bloqueo de login por email.

Revision ID: 0006_v2_auth_hardening
Revises: 0005_v2_recommendations
Create Date: 2026-10-04
"""
from alembic import op

from migrations.sql_runner import SQL_DIR, run_sql_file

revision = "0006_v2_auth_hardening"
down_revision = "0005_v2_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0006_v2_auth_hardening.sql")


def downgrade() -> None:
    # Restaura purge_run de 0005 (la de 0006 limpia tablas que se borran aquí)
    sql = (SQL_DIR / "0005_v2_recommendations.sql").read_text(encoding="utf-8")
    start = sql.index("CREATE OR REPLACE FUNCTION api.purge_run")
    end = sql.index("-- Permisos explícitos")
    op.get_bind().connection.driver_connection.cursor().execute(sql[start:end])
    for fn in ("rate_limit_hit(bytea, integer, integer)", "login_throttle_status(bytea)",
               "login_throttle_fail(bytea)", "login_throttle_clear(bytea)", "_lock_minutes(integer)"):
        op.execute(f"DROP FUNCTION IF EXISTS api.{fn}")
    op.execute("DROP TABLE IF EXISTS rate_limit, login_throttle")
