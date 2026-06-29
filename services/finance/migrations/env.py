import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ensure the repo root is importable as `services.*` regardless of cwd.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from services.finance.database import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# All services share one physical Postgres database (DATABASE_URL), so each
# service's Alembic history must use its own version table to avoid
# colliding with other services' migration state.
VERSION_TABLE = "alembic_version_finance"

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL", config.get_main_option("sqlalchemy.url")
    ).replace("postgresql+asyncpg://", "postgresql://")


def include_name(name, type_, parent_names):
    """Restrict autogenerate to tables this service actually owns.

    All services share one physical Postgres database, so without this
    filter, autogenerate would reflect every other service's tables too and
    propose dropping anything not in this service's own metadata.
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
