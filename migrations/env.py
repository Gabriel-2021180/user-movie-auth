from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.session import _psycopg3_url

# Las migraciones corren con el usuario dueño de la BD (DATABASE_URL).
# Son SQL explícito (migrations/sql), no autogeneradas desde los modelos.


def run_migrations_offline() -> None:
    context.configure(url=_psycopg3_url(settings.DATABASE_URL), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        _psycopg3_url(settings.DATABASE_URL),
        poolclass=pool.NullPool,
        connect_args={"prepare_threshold": None},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
