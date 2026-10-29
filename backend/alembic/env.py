"""Alembic-Umgebung: verbindet Migrationen mit unserem Datenmodell.

Nach „Full Stack Handwerk“, S. 104: env.py importiert das Datenmodell,
damit autogenerate die Tabellen sieht, und nutzt dieselbe
Verbindungsadresse wie die Anwendung (app/db.py) statt des Platzhalters
sqlalchemy.url in alembic.ini.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app.db import database_url
from app.models import Base

# Zugriff auf die Werte aus alembic.ini (hier nur das Logging)
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Unser Datenmodell: daraus erzeugt autogenerate die Migrationen
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Erzeugt nur das SQL als Text, ohne Verbindung zur Datenbank."""
    context.configure(
        url=database_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Verbindet sich mit der Datenbank und führt die Migrationen aus."""
    connectable = create_engine(database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()