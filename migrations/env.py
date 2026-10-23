"""Alembic environment configured from the workspace database URL."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src import config
from src.core.db import Base


alembic_config = context.config
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

database_url = config.opt("DATABASE_URL") or alembic_config.get_main_option("sqlalchemy.url")
alembic_config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating a DBAPI connection."""
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using an engine connection."""
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}) or {},
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
