from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.session import _psycopg3_url

# Las migraciones corren con el usuario dueño de la BD (DATABASE_URL, o DATABASE_URL_DEV con DB_TARGET=dev).
# Son SQL explícito (migrations/sql), no autogeneradas desde los modelos.


def run_migrations_offline() -> None:
    context.configure(url=_psycopg3_url(settings.owner_database_url), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _guard_production() -> None:
    """Producción solo se migra con confirmación explícita: alembic -x confirm_prod=yes upgrade head"""
    if settings.DB_TARGET == "prod" and context.get_x_argument(as_dictionary=True).get("confirm_prod") != "yes":
        raise SystemExit(
            "Bloqueado: DB_TARGET=prod apunta a PRODUCCIÓN. "
            "Usa DB_TARGET=dev, o confirma con: alembic -x confirm_prod=yes upgrade head"
        )


def run_migrations_online() -> None:
    _guard_production()
    print(f"Migrando BD: target={settings.DB_TARGET}")
    engine = create_engine(
        _psycopg3_url(settings.owner_database_url),
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
