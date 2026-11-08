"""Fixtures für Integrationstests gegen PostgreSQL.

Die Tests laufen nur, wenn INTEGRATION_DB=1 gesetzt ist (Compose-Service
"test" mit eigener Testdatenbank "db-test"); sonst werden sie übersprungen.
Das Schema entsteht wie im Betrieb über alembic upgrade head, damit die
Migrationen mitgeprüft werden.

Zwei Arten von Client:
- pg_client: leere Tabellen vor jedem einzelnen Test.
- pg_module_client: leere Tabellen einmal pro Testdatei. Für Prüfabläufe,
  deren Daten (Serien mit Suchen) nur einmal gerechnet werden sollen.
"""

import os

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.db import database_url
from app.main import app
from pg_setup import ENABLE_VAR, alembic_config, require_test_database, truncate_all


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
    truncate_all(pg_engine)
    return pg_engine


@pytest.fixture
def pg_client(pg_clean):
    """TestClient gegen die echte App-Session (get_session ohne Ersatz)."""
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def pg_module_client(pg_engine):
    """Wie pg_client, Tabellen aber nur einmal pro Testdatei geleert."""
    truncate_all(pg_engine)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client