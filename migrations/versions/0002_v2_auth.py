"""v2 auth: esquema api, rol movie_api_runtime, refresh tokens, códigos y consentimientos.

Revision ID: 0002_v2_auth
Revises: 0001_baseline
Create Date: 2026-10-03
"""
from alembic import op

from migrations.sql_runner import run_sql_file

revision = "0002_v2_auth"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql_file("0002_v2_auth.sql")


def downgrade() -> None:
    # Destructivo: borra sesiones, códigos y consentimientos de v2. No correr en producción sin respaldo.
    op.execute("DROP SCHEMA IF EXISTS api CASCADE")
    op.execute("DROP TABLE IF EXISTS refresh_token, verification_code, user_consent")
    op.execute("DROP INDEX IF EXISTS user_email_lower_uq, user_username_lower_uq, "
               "favorite_user_idx, review_user_idx, review_movie_idx")
    op.execute('ALTER TABLE "user" DROP CONSTRAINT IF EXISTS user_account_status_chk')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS bio, DROP COLUMN IF EXISTS favorite_genres, '
               'DROP COLUMN IF EXISTS onboarding_completed, DROP COLUMN IF EXISTS account_status, '
               'DROP COLUMN IF EXISTS deactivated_at, DROP COLUMN IF EXISTS password_changed_at')
