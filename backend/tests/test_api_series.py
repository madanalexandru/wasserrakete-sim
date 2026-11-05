"""API-Tests: Serie starten (POST /api/rockets/{id}/series) und abrufen
(GET /api/series/{id}).

Wie test_api_flights.py gegen SQLite im Arbeitsspeicher; die Fixtures sind
bewusst kopiert statt importiert, damit die Dateien unabhängig bleiben.

Geprüft wird: ein Flug pro Schritt mit series_id, nur der variierte
Parameter ändert sich, Ergebnisse wie die Physik; duration_s umfasst die
Simulationen, nicht die Vorabprüfung; alles oder nichts: ungültiger
Schritt (vor jeder Rechnung) und Simulationsfehler -> 422 mit
Schrittnummer, nichts gespeichert; andere Fehler -> 500, nichts
gespeichert. Abruf: dieselbe Serie wie der POST, rechnet nichts; unbekannte
ID -> 404.

Die Fehlerfälle der Simulation ersetzen simulate_flight per monkeypatch:
Ein echter RuntimeError (z. B. Düse 0,1 mm) braucht rund eine Minute.

Werte frei gewählt, NICHT gemessen.
"""

from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main
from app.db import get_session
from app.main import app
from app.models import (
    CONFIG_FIELDS, GEOMETRY_FIELDS, RESULT_FIELDS, Base, Flight, Series, result_values,
)
from app.physics.simulation import EXAMPLE_ROCKET, MODEL_VERSION, simulate_flight
from app.schemas import SeriesCreate, SeriesRead

GEOMETRY = dict(
    nose_shape="cone", l_nose=0.12, n_fins=3, fin_root_chord=0.10,
    fin_tip_chord=0.05, fin_span=0.08, fin_sweep=0.05, x_fin=0.30,
    x_cg_empty=0.20, l_total=0.42,
)
REQUIRED = {k: v for k, v in asdict(EXAMPLE_ROCKET).items() if k not in GEOMETRY_FIELDS}
MINIMAL = {"name": "Testrakete", **REQUIRED}
FULL = {**MINIMAL, **GEOMETRY}

SERIES = dict(
    name="Druckserie", mode="forward", param_name="p0_gauge",
    param_start=2e5, param_stop=6e5, n_steps=3,
)


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


def count(engine, table) -> int:
    with Session(engine) as session:  # frische Session, unabhängig von der App
        return session.scalar(select(func.count()).select_from(table))


def flights_of(engine, series_id: int) -> list[Flight]:
    with Session(engine) as session:
        query = select(Flight).where(Flight.series_id == series_id).order_by(Flight.id)
        return list(session.scalars(query))


def new_rocket(client, payload=FULL) -> int:
    response = client.post("/api/rockets", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def start_series(client, rocket_id: int, **changes):
    return client.post(f"/api/rockets/{rocket_id}/series", json={**SERIES, **changes})


# --- Erfolgsfall -------------------------------------------------------------

def test_series_returns_201_with_series(client):
    rocket_id = new_rocket(client)
    response = start_series(client, rocket_id)
    assert response.status_code == 201
    body = response.json()
    assert list(body) == list(SeriesRead.model_fields)
    assert body["rocket_id"] == rocket_id
    assert body["mode"] == "forward"
    assert body["param_name"] == "p0_gauge"
    assert body["n_steps"] == 3
    assert body["searcher"] is None


def test_series_is_really_stored(client, engine):
    body = start_series(client, new_rocket(client)).json()
    with Session(engine) as session:
        row = session.get(Series, body["id"])
        stored = SeriesRead.model_validate(row).model_dump(mode="json")
    stored.pop("created_at")
    assert stored == {k: v for k, v in body.items() if k != "created_at"}


def test_one_flight_per_step_with_series_id(client, engine):
    body = start_series(client, new_rocket(client), n_steps=4).json()
    flights = flights_of(engine, body["id"])
    assert len(flights) == 4
    assert count(engine, Flight) == 4
    assert all(f.model_version == MODEL_VERSION for f in flights)


def test_flights_vary_only_the_param(client, engine):
    rocket_id = new_rocket(client)
    body = start_series(client, rocket_id).json()
    flights = flights_of(engine, body["id"])
    assert [f.p0_gauge for f in flights] == [2e5, 4e5, 6e5]
    for f in flights:
        assert f.rocket_id == rocket_id
        for name in CONFIG_FIELDS:
            if name != "p0_gauge":
                assert getattr(f, name) == FULL[name]


def test_flights_without_geometry_keep_null(client, engine):
    body = start_series(client, new_rocket(client, MINIMAL)).json()
    for f in flights_of(engine, body["id"]):
        assert all(getattr(f, name) is None for name in GEOMETRY_FIELDS)


def test_results_equal_physics(client, engine):
    body = start_series(client, new_rocket(client), param_name="c_w",
                        param_start=0.3, param_stop=0.7).json()
    for f in flights_of(engine, body["id"]):
        expected = result_values(simulate_flight(replace(EXAMPLE_ROCKET, c_w=f.c_w)))
        assert {name: getattr(f, name) for name in RESULT_FIELDS} == expected


def test_inverse_fields_are_null(client, engine):
    body = start_series(client, new_rocket(client)).json()
    for f in flights_of(engine, body["id"]):
        assert f.target_apogee is None
        assert f.searcher is None
        assert f.search_evaluations is None


def test_duration_is_stored(client):
    body = start_series(client, new_rocket(client)).json()
    assert body["duration_s"] > 0


def test_duration_covers_simulations_not_validation(client, monkeypatch):
    # Gestellte Uhr: jede Simulation dauert 1 s, die Vorabprüfung 100 s.
    clock = {"t": 0.0}
    real_step_configs = SeriesCreate.step_configs

    def slow_step_configs(self, rocket):
        clock["t"] += 100.0
        return real_step_configs(self, rocket)

    def slow_simulation(cfg):
        clock["t"] += 1.0
        return simulate_flight(cfg)

    monkeypatch.setattr(main, "perf_counter", lambda: clock["t"])
    monkeypatch.setattr(main, "simulate_flight", slow_simulation)
    monkeypatch.setattr(SeriesCreate, "step_configs", slow_step_configs)
    body = start_series(client, new_rocket(client), n_steps=3).json()
    assert body["duration_s"] == 3.0


def test_each_series_has_its_own_flights(client, engine):
    rocket_id = new_rocket(client)
    first = start_series(client, rocket_id, n_steps=2).json()
    second = start_series(client, rocket_id, n_steps=3).json()
    assert first["id"] != second["id"]
    assert len(flights_of(engine, first["id"])) == 2
    assert len(flights_of(engine, second["id"])) == 3


def test_series_flights_are_readable_as_single_flights(client, engine):
    body = start_series(client, new_rocket(client)).json()
    flight_id = flights_of(engine, body["id"])[0].id
    response = client.get(f"/api/flights/{flight_id}")
    assert response.status_code == 200
    assert response.json()["series_id"] == body["id"]


# --- Fehlerfälle -------------------------------------------------------------

def test_unknown_rocket_404(client, engine):
    response = start_series(client, 999999)
    assert response.status_code == 404
    assert response.json() == {"detail": "Rakete nicht gefunden"}
    assert count(engine, Series) == 0


def test_rocket_id_must_be_integer(client):
    assert client.post("/api/rockets/abc/series", json=SERIES).status_code == 422


@pytest.mark.parametrize("changes", [
    {"n_steps": 1}, {"mode": "inverse"}, {"param_name": "l_nose"},
    {"param_start": 6e5, "param_stop": 2e5}, {"searcher": "binary"},
])
def test_invalid_body_gives_422_and_stores_nothing(client, engine, changes):
    response = start_series(client, new_rocket(client), **changes)
    assert response.status_code == 422
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


def test_invalid_body_is_checked_before_rocket(client):
    # FastAPI prüft den Body, bevor der Endpunkt die Rakete sucht
    assert start_series(client, 999999, n_steps=1).status_code == 422


def test_invalid_step_gives_422_before_any_simulation(client, engine, monkeypatch):
    rocket_id = new_rocket(client, MINIMAL)

    def must_not_run(cfg):
        raise AssertionError("darf vor der Vorabprüfung nicht rechnen")

    monkeypatch.setattr(main, "simulate_flight", must_not_run)
    # v_bottle 1,5 l; Schritt 3 (1,6 l Wasser) verletzt v_water0 < v_bottle
    response = start_series(client, rocket_id, param_name="v_water0",
                            param_start=1e-4, param_stop=1.6e-3, n_steps=4)
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 3]
    assert detail["type"] == "value_error"
    assert detail["msg"].startswith("Schritt 3 (v_water0 = 0.0016)")
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


@pytest.mark.parametrize("error", [ValueError, RuntimeError])
def test_simulation_error_gives_422_and_stores_nothing(client, engine, monkeypatch, error):
    rocket_id = new_rocket(client)
    calls = {"n": 0}

    def fails_at_third_step(cfg):
        calls["n"] += 1
        if calls["n"] == 3:
            raise error("max_steps zu klein")
        return simulate_flight(cfg)

    monkeypatch.setattr(main, "simulate_flight", fails_at_third_step)
    response = start_series(client, rocket_id, n_steps=4)
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 2]
    assert detail["type"] == "simulation_error"
    assert detail["msg"] == "Schritt 2 (p0_gauge = 466666.6666666667): max_steps zu klein"
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


def test_other_errors_stay_500_and_store_nothing(engine, monkeypatch):
    def broken_simulation(cfg):
        raise ZeroDivisionError("Programmierfehler")

    try:
        with make_client(engine, raise_server_exceptions=False) as c:
            rocket_id = new_rocket(c)
            monkeypatch.setattr(main, "simulate_flight", broken_simulation)
            assert start_series(c, rocket_id).status_code == 500
    finally:
        app.dependency_overrides.clear()
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


# --- Abruf -------------------------------------------------------------------

def test_get_returns_same_series_as_post(client):
    posted = start_series(client, new_rocket(client)).json()
    response = client.get(f"/api/series/{posted['id']}")
    assert response.status_code == 200
    assert response.json() == posted


def test_get_does_not_compute(client, engine, monkeypatch):
    posted = start_series(client, new_rocket(client)).json()

    def must_not_run(cfg):
        raise AssertionError("GET darf nicht rechnen")

    monkeypatch.setattr(main, "simulate_flight", must_not_run)
    assert client.get(f"/api/series/{posted['id']}").json() == posted
    assert count(engine, Flight) == 3


@pytest.mark.parametrize("series_id", [999999, 0, -1])
def test_unknown_series_404(client, series_id):
    response = client.get(f"/api/series/{series_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Serie nicht gefunden"}


def test_series_id_must_be_integer(client):
    assert client.get("/api/series/abc").status_code == 422