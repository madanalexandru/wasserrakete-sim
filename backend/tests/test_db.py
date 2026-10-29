"""Tests für die Datenbankverbindung (app/db.py).

Diese Tests brauchen keine laufende Datenbank: Sie prüfen nur, wie die
Verbindungsadresse gebaut wird. Die echte Verbindung wird im Stack mit
docker compose geprüft.
"""

import pytest

from app import db

ENV = {
    "POSTGRES_USER": "rakete",
    "POSTGRES_PASSWORD": "geheim",
    "POSTGRES_DB": "wasserrakete",
}


@pytest.fixture
def env(monkeypatch):
    for name in ("POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    db.get_engine.cache_clear()
    yield monkeypatch
    db.get_engine.cache_clear()


def test_url_from_env(env):
    url = db.database_url()
    assert url.drivername == "postgresql+psycopg2"
    assert url.username == "rakete"
    assert url.password == "geheim"
    assert url.database == "wasserrakete"


def test_default_host_is_compose_service(env):
    url = db.database_url()
    assert url.host == "db"
    assert url.port == 5432


def test_host_and_port_overridable(env):
    env.setenv("POSTGRES_HOST", "localhost")
    env.setenv("POSTGRES_PORT", "5433")
    url = db.database_url()
    assert (url.host, url.port) == ("localhost", 5433)


def test_special_characters_in_password(env):
    env.setenv("POSTGRES_PASSWORD", "p@ss/w:rd#1")
    url = db.database_url()
    assert url.password == "p@ss/w:rd#1"
    assert url.host == "db"  # @ im Passwort verschiebt den Host nicht


@pytest.mark.parametrize("name", ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"])
def test_missing_variable_is_reported(env, name):
    env.delenv(name)
    with pytest.raises(RuntimeError, match=name):
        db.database_url()


def test_password_hidden_in_text(env):
    assert "geheim" not in str(db.database_url())


def test_engine_created_without_connecting(env):
    env.setenv("POSTGRES_HOST", "host-den-es-nicht-gibt")
    engine = db.get_engine()  # verbindet erst bei der ersten Abfrage
    assert engine.url.host == "host-den-es-nicht-gibt"
    assert db.get_engine() is engine