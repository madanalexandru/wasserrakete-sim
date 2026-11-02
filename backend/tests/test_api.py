"""API-Tests: Rakete anlegen (POST) und abrufen (GET).

Die Tests laufen gegen SQLite im Arbeitsspeicher, nicht gegen PostgreSQL
(Entscheidung 1C, Chat 02.11.2026). FastAPI ersetzt dafür get_session
durch eine SQLite-Session (dependency_overrides). Integrationstests gegen
das echte PostgreSQL folgen in einem eigenen Schritt.

StaticPool + check_same_thread=False: Eine SQLite-Datenbank im Speicher
lebt nur in ihrer Verbindung. TestClient ruft die App aus einem anderen
Thread auf; so sehen Test und App dieselbe Verbindung und dieselben Daten.

Werte frei gewählt (wie test_stability.py), NICHT gemessen.
"""

from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import CONFIG_FIELDS, GEOMETRY_FIELDS, Base, Rocket
from app.physics.airphase import T_START
from app.physics.simulation import EXAMPLE_ROCKET
from app.schemas import RocketCreate

GEOMETRY = dict(
    nose_shape="cone", l_nose=0.12, n_fins=3, fin_root_chord=0.10,
    fin_tip_chord=0.05, fin_span=0.08, fin_sweep=0.05, x_fin=0.30,
    x_cg_empty=0.20, l_total=0.42,
)
REQUIRED = {k: v for k, v in asdict(EXAMPLE_ROCKET).items() if k not in GEOMETRY_FIELDS}
MINIMAL = {"name": "Testrakete", **REQUIRED}
FULL = {**MINIMAL, **GEOMETRY}


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    def sqlite_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sqlite_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def count_rockets(engine) -> int:
    with Session(engine) as session:  # frische Session, unabhängig von der App
        return session.scalar(select(func.count()).select_from(Rocket))


# --- Anlegen --------------------------------------------------------------

def test_create_returns_201_with_id(client):
    response = client.post("/api/rockets", json=FULL)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["created_at"]


def test_create_returns_sent_values(client):
    body = client.post("/api/rockets", json=FULL).json()
    assert body["name"] == "Testrakete"
    assert {k: body[k] for k in CONFIG_FIELDS} == {k: FULL[k] for k in CONFIG_FIELDS}


def test_create_without_geometry(client):
    data = {k: v for k, v in MINIMAL.items() if k != "temp0"}
    response = client.post("/api/rockets", json=data)
    assert response.status_code == 201
    body = response.json()
    assert all(body[k] is None for k in GEOMETRY_FIELDS)
    assert body["temp0"] == T_START


def test_rocket_is_really_stored(client, engine):
    rocket_id = client.post("/api/rockets", json=FULL).json()["id"]
    with Session(engine) as session:
        stored = session.get(Rocket, rocket_id)
        assert stored is not None
        assert stored.name == "Testrakete"
        assert stored.to_config() == RocketCreate(**FULL).to_config()


def test_two_rockets_get_different_ids(client, engine):
    first = client.post("/api/rockets", json=FULL).json()["id"]
    second = client.post("/api/rockets", json=MINIMAL).json()["id"]
    assert first != second
    assert count_rockets(engine) == 2


# --- Abrufen --------------------------------------------------------------

def test_get_returns_created_rocket(client):
    created = client.post("/api/rockets", json=FULL).json()
    response = client.get(f"/api/rockets/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_id_returns_404(client):
    response = client.get("/api/rockets/999")
    assert response.status_code == 404


def test_get_non_numeric_id_returns_422(client):
    assert client.get("/api/rockets/abc").status_code == 422


# --- Ungültige Eingaben: 422, nichts gespeichert --------------------------

@pytest.mark.parametrize("changes", [
    {"v_water0": 2.0e-3},          # mehr Wasser als Flasche
    {"d_nozzle": 0.10},            # Düse breiter als Rumpf
    {"n_fins": 5},
    {"l_total": None},             # Geometrie unvollständig
    {"x_cg_empty": 0.50},          # Schwerpunkt außerhalb der Rakete
    {"fin_sweeep": 0.05},          # unbekanntes Feld (Tippfehler)
    {"p0_gauge": -1.0},
])
def test_invalid_input_returns_422_and_stores_nothing(client, engine, changes):
    response = client.post("/api/rockets", json={**FULL, **changes})
    assert response.status_code == 422
    assert count_rockets(engine) == 0


def test_missing_required_field_returns_422(client, engine):
    data = {k: v for k, v in FULL.items() if k != "p0_gauge"}
    response = client.post("/api/rockets", json=data)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "p0_gauge"]
    assert count_rockets(engine) == 0


def test_422_message_names_the_problem(client):
    response = client.post("/api/rockets", json={**FULL, "l_total": None})
    message = response.json()["detail"][0]["msg"]
    assert "unvollständig" in message
    assert "l_total" in message