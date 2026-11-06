"""API-Tests: Flugkurve abrufen (GET /api/flights/{id}/trajectory).

Wie test_api_flights.py gegen SQLite im Arbeitsspeicher. Die Fixtures sind
bewusst kopiert statt importiert, damit die Dateien unabhängig bleiben.

Geprüft wird: Antwortform (Feldreihenfolge, drei gleich lange Listen,
höchstens MAX_POINTS Punkte); Kurve = ausgedünnte Kurve der Physik für die
gespeicherte Konfiguration; Start bei t = 0, h = 0; Zeit steigend; letzter
Punkt = gespeichertes Apogäum mit v = 0; auch für Flüge einer Serie;
andere Modellversion -> 409 ohne Neurechnung; Apogäum passt nicht -> 500;
Fehler beim Neurechnen -> 500 (kein Sicherheitsnetz); nichts wird
gespeichert oder verändert; unbekannte ID -> 404, keine Zahl -> 422.

Höhen werden nur verglichen, nie ausgegeben: Die Fehlermeldungen nennen
keine Werte, damit kein Apogäum sichtbar wird.

Werte frei gewählt (wie test_api.py), NICHT gemessen.
"""

from dataclasses import asdict, replace
from math import inf, nextafter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import GEOMETRY_FIELDS, Base, Flight
from app.physics.simulation import EXAMPLE_ROCKET, MODEL_VERSION, simulate_flight
from app.schemas import FlightRead, RocketCreate, TrajectoryRead
from app.trajectory import MAX_POINTS, thin_trajectory

REQUIRED = {k: v for k, v in asdict(EXAMPLE_ROCKET).items() if k not in GEOMETRY_FIELDS}
MINIMAL = {"name": "Testrakete", **REQUIRED}


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


@pytest.fixture
def client_500(engine):
    # Zeigt Serverfehler als Status 500 wie ein echter Client
    with make_client(engine, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def count_flights(engine) -> int:
    with Session(engine) as session:  # frische Session, unabhängig von der App
        return session.scalar(select(func.count()).select_from(Flight))


def new_flight(client, payload=MINIMAL) -> dict:
    rocket = client.post("/api/rockets", json=payload)
    assert rocket.status_code == 201
    flight = client.post(f"/api/rockets/{rocket.json()['id']}/flights")
    assert flight.status_code == 201
    return flight.json()


def get_trajectory(client, flight_id):
    return client.get(f"/api/flights/{flight_id}/trajectory")


# --- Antwortform -------------------------------------------------------------

def test_returns_200_with_fields_in_order(client):
    response = get_trajectory(client, new_flight(client)["id"])
    assert response.status_code == 200
    assert list(response.json()) == list(TrajectoryRead.model_fields)


def test_head_matches_flight(client):
    flight = new_flight(client)
    body = get_trajectory(client, flight["id"]).json()
    assert body["flight_id"] == flight["id"]
    assert body["model_version"] == flight["model_version"] == MODEL_VERSION


def test_lists_equally_long_and_thinned(client):
    body = get_trajectory(client, new_flight(client)["id"]).json()
    assert len(body["t"]) == len(body["h"]) == len(body["v"])
    assert 2 <= len(body["t"]) <= MAX_POINTS


# --- Inhalt ------------------------------------------------------------------

def test_equals_thinned_physics(client):
    # Gleicher Code, gleiche Eingabe -> exakt gleiche Kurve (deterministisch)
    body = get_trajectory(client, new_flight(client)["id"]).json()
    points = thin_trajectory(simulate_flight(RocketCreate(**MINIMAL).to_config()).trajectory)
    same = list(zip(body["t"], body["h"], body["v"])) == points
    assert same, "Kurve weicht von der Physik ab"


def test_starts_on_the_ground(client):
    body = get_trajectory(client, new_flight(client)["id"]).json()
    assert (body["t"][0], body["h"][0], body["v"][0]) == (0.0, 0.0, 0.0)


def test_time_strictly_increasing(client):
    t = get_trajectory(client, new_flight(client)["id"]).json()["t"]
    assert all(a < b for a, b in zip(t, t[1:]))


def test_ends_at_stored_apogee(client):
    flight = new_flight(client)
    body = get_trajectory(client, flight["id"]).json()
    same = (
        body["h"][-1] == flight["apogee"]
        and body["t"][-1] == flight["t_apogee"]
        and body["v"][-1] == 0.0
    )
    assert same, "letzter Punkt ist nicht das gespeicherte Apogäum"


def test_flight_of_a_series(client, engine):
    rocket_id = client.post("/api/rockets", json=MINIMAL).json()["id"]
    series = client.post(
        f"/api/rockets/{rocket_id}/series",
        json={"name": "Kurve", "mode": "forward", "param_name": "c_w",
              "param_start": 0.3, "param_stop": 0.6, "n_steps": 2},
    )
    assert series.status_code == 201
    with Session(engine) as session:
        flights = session.scalars(select(Flight).order_by(Flight.id)).all()
        stored = [(f.id, f.apogee) for f in flights]
    assert len(stored) == 2
    for flight_id, apogee in stored:
        body = get_trajectory(client, flight_id).json()
        same = body["h"][-1] == apogee
        assert same, "Serienflug: letzter Punkt ist nicht das gespeicherte Apogäum"


# --- Modellversion und Konsistenz --------------------------------------------

def test_other_model_version_gives_409_without_recompute(client, monkeypatch):
    flight = new_flight(client)

    def must_not_run(cfg):
        raise AssertionError("bei anderer Modellversion darf nicht gerechnet werden")

    monkeypatch.setattr("app.main.simulate_flight", must_not_run)
    monkeypatch.setattr("app.main.MODEL_VERSION", "neu")
    response = get_trajectory(client, flight["id"])
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert f"Modellversion {MODEL_VERSION} gerechnet" in detail
    assert "aktuell neu" in detail


def test_apogee_mismatch_gives_500(client_500, monkeypatch):
    flight = new_flight(client_500)
    real = simulate_flight

    def shifted(cfg):
        # kleinste mögliche Abweichung: die nächste darstellbare Zahl
        result = real(cfg)
        return replace(result, apogee=nextafter(result.apogee, inf))

    monkeypatch.setattr("app.main.simulate_flight", shifted)
    response = get_trajectory(client_500, flight["id"])
    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Neu gerechnete Flugkurve passt nicht zum gespeicherten Apogäum"
    )


@pytest.mark.parametrize("error", [ValueError, RuntimeError])
def test_error_on_recompute_gives_500(client_500, monkeypatch, error):
    # Kein Sicherheitsnetz: Der Flug war beim Speichern rechenbar
    flight = new_flight(client_500)

    def broken(cfg):
        raise error("kaputt")

    monkeypatch.setattr("app.main.simulate_flight", broken)
    assert get_trajectory(client_500, flight["id"]).status_code == 500


# --- Nichts wird verändert ---------------------------------------------------

def test_changes_nothing(client, engine):
    flight = new_flight(client)
    get_trajectory(client, flight["id"])
    get_trajectory(client, flight["id"])
    assert count_flights(engine) == 1
    with Session(engine) as session:  # frische Session: nicht der Antwort glauben
        stored = FlightRead.model_validate(session.get(Flight, flight["id"]))
    stored = stored.model_dump(mode="json")
    stored.pop("created_at")  # SQLite speichert ohne Zeitzone (Dialektunterschied)
    flight.pop("created_at")
    assert stored == flight


def test_flight_get_still_without_trajectory(client):
    flight = new_flight(client)
    get_trajectory(client, flight["id"])
    assert "trajectory" not in client.get(f"/api/flights/{flight['id']}").json()


# --- Unbekannte und ungültige IDs --------------------------------------------

@pytest.mark.parametrize("flight_id", [1, 999, 0, -1])
def test_unknown_flight_gives_404(client, flight_id):
    response = get_trajectory(client, flight_id)
    assert response.status_code == 404
    assert response.json() == {"detail": "Flug nicht gefunden"}


def test_not_a_number_gives_422(client):
    assert get_trajectory(client, "abc").status_code == 422