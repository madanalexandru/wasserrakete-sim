"""API-Tests: Flug simulieren (POST /api/rockets/{id}/flights).

Wie test_api.py gegen SQLite im Arbeitsspeicher. Die Fixtures sind bewusst
aus test_api.py kopiert statt importiert, damit beide Dateien unabhängig
bleiben.

Geprüft wird: URL unter der Rakete ohne Body; Flug = exakte Kopie der
Rakete; model_version aus simulation.py; Antwort = vollständiger Kassenbon
ohne Flugkurve; ValueError/RuntimeError der Simulation -> 422, nichts
gespeichert; andere Fehler -> 500.

Die Fehlerfälle ersetzen simulate_flight per monkeypatch: Ein echter
RuntimeError (z. B. Düse 0,1 mm) braucht rund eine Minute, zu lang für
einen Test.

Werte frei gewählt (wie test_api.py), NICHT gemessen.
"""

from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import CONFIG_FIELDS, GEOMETRY_FIELDS, RESULT_FIELDS, Base, Flight
from app.physics.simulation import EXAMPLE_ROCKET, MODEL_VERSION, simulate_flight
from app.schemas import FlightRead, RocketCreate

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


def make_client(engine, **kwargs):
    def sqlite_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sqlite_session
    return TestClient(app, **kwargs)


@pytest.fixture
def client(engine):
    with make_client(engine) as c:
        yield c
    app.dependency_overrides.clear()


def count_flights(engine) -> int:
    with Session(engine) as session:  # frische Session, unabhängig von der App
        return session.scalar(select(func.count()).select_from(Flight))


def new_rocket(client, payload=FULL) -> int:
    response = client.post("/api/rockets", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


# --- Erfolgsfall -------------------------------------------------------------

def test_flight_returns_201_with_receipt(client):
    rocket_id = new_rocket(client)
    response = client.post(f"/api/rockets/{rocket_id}/flights")
    assert response.status_code == 201
    body = response.json()
    assert list(body) == list(FlightRead.model_fields)  # vollständiger Kassenbon
    assert isinstance(body["id"], int)
    assert body["created_at"]
    assert body["rocket_id"] == rocket_id
    assert body["series_id"] is None  # Einzelflug


def test_model_version_is_stored(client):
    body = client.post(f"/api/rockets/{new_rocket(client)}/flights").json()
    assert body["model_version"] == MODEL_VERSION


def test_inverse_fields_are_null(client):
    body = client.post(f"/api/rockets/{new_rocket(client)}/flights").json()
    assert body["target_apogee"] is None
    assert body["searcher"] is None
    assert body["search_evaluations"] is None


def test_config_is_copy_of_rocket(client):
    body = client.post(f"/api/rockets/{new_rocket(client)}/flights").json()
    expected = RocketCreate(**FULL).to_config()
    assert {k: body[k] for k in CONFIG_FIELDS} == asdict(expected)


def test_config_copy_without_geometry(client):
    body = client.post(f"/api/rockets/{new_rocket(client, MINIMAL)}/flights").json()
    assert all(body[k] is None for k in GEOMETRY_FIELDS)


def test_result_equals_physics(client):
    # Gleicher Code, gleiche Eingabe -> exakt gleiche Zahlen (deterministisch)
    body = client.post(f"/api/rockets/{new_rocket(client)}/flights").json()
    result = simulate_flight(RocketCreate(**FULL).to_config())
    assert {k: body[k] for k in RESULT_FIELDS} == {k: getattr(result, k) for k in RESULT_FIELDS}


def test_no_trajectory_in_response(client):
    body = client.post(f"/api/rockets/{new_rocket(client)}/flights").json()
    assert "trajectory" not in body


def test_flight_is_really_stored(client, engine):
    body = client.post(f"/api/rockets/{new_rocket(client)}/flights").json()
    with Session(engine) as session:  # frische Session: nicht der Antwort glauben
        row = session.get(Flight, body["id"])
        stored = FlightRead.model_validate(row).model_dump(mode="json")
    body.pop("created_at")
    stored.pop("created_at")  # SQLite speichert ohne Zeitzone (Dialektunterschied)
    assert stored == body


def test_each_post_creates_new_flight(client, engine):
    rocket_id = new_rocket(client)
    first = client.post(f"/api/rockets/{rocket_id}/flights").json()
    second = client.post(f"/api/rockets/{rocket_id}/flights").json()
    assert first["id"] != second["id"]
    assert first["apogee"] == second["apogee"]
    assert count_flights(engine) == 2


# --- Fehlerfälle -------------------------------------------------------------

def test_unknown_rocket_404(client, engine):
    response = client.post("/api/rockets/999/flights")
    assert response.status_code == 404
    assert count_flights(engine) == 0


def test_rocket_id_must_be_integer(client):
    assert client.post("/api/rockets/abc/flights").status_code == 422


def test_body_is_ignored(client):
    # Keine Überschreibungen: Ein Body ändert nichts am Flug
    rocket_id = new_rocket(client)
    body = client.post(f"/api/rockets/{rocket_id}/flights", json={"p0_gauge": 1.0}).json()
    assert body["p0_gauge"] == FULL["p0_gauge"]


@pytest.mark.parametrize("error", [RuntimeError, ValueError])
def test_simulation_error_gives_422_and_stores_nothing(client, engine, monkeypatch, error):
    rocket_id = new_rocket(client)

    def failing_simulation(cfg):
        raise error("Wasserphase nicht beendet: max_steps zu klein.")

    monkeypatch.setattr("app.main.simulate_flight", failing_simulation)
    response = client.post(f"/api/rockets/{rocket_id}/flights")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["path", "rocket_id"]
    assert "max_steps" in detail[0]["msg"]
    assert detail[0]["type"] == "simulation_error"
    assert count_flights(engine) == 0


def test_other_errors_stay_500(engine, monkeypatch):
    # Programmierfehler sollen sichtbar bleiben (kein globaler Handler)
    def broken_simulation(cfg):
        raise ZeroDivisionError("Programmierfehler")

    try:
        with make_client(engine, raise_server_exceptions=False) as c:
            rocket_id = new_rocket(c)
            monkeypatch.setattr("app.main.simulate_flight", broken_simulation)
            assert c.post(f"/api/rockets/{rocket_id}/flights").status_code == 500
    finally:
        app.dependency_overrides.clear()
    assert count_flights(engine) == 0