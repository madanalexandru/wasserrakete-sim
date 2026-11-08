"""Fixtures für Integrationstests gegen PostgreSQL.

Die Tests laufen nur, wenn INTEGRATION_DB=1 gesetzt ist (Compose-Service
"test" mit eigener Testdatenbank "db-test"); sonst werden sie übersprungen.
Das Schema entsteht wie im Betrieb über alembic upgrade head, damit die
Migrationen mitgeprüft werden. Vor jedem Test werden alle Tabellen geleert.
"""

import os

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.db import database_url
from app.main import app
from pg_setup import ENABLE_VAR, alembic_config, require_test_database

# Reihenfolge egal, CASCADE folgt den Fremdschlüsseln.
TABLES = ("flights", "series", "rockets")


@pytest.fixture(scope="session")
def pg_engine():
    """Engine auf die Testdatenbank, Schema auf dem neuesten Stand."""
    if os.environ.get(ENABLE_VAR) != "1":
        pytest.skip(f"Integrationstest: {ENABLE_VAR}=1 ist nicht gesetzt")
    url = database_url()
    require_test_database(url)  # vor jedem Schreibzugriff
    command.upgrade(alembic_config(), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_clean(pg_engine):
    """Leere Tabellen und IDs ab 1, unabhängig von früheren Läufen."""
    with pg_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    return pg_engine


@pytest.fixture
def pg_client(pg_clean):
    """TestClient gegen die echte App-Session (get_session ohne Ersatz)."""
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client