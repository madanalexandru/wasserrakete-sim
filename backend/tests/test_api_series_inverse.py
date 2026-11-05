"""API-Tests: Serie im inversen Modus (POST /api/rockets/{id}/series).

Wie test_api_series.py gegen SQLite im Arbeitsspeicher; die Fixtures sind
bewusst kopiert statt importiert, damit die Dateien unabhängig bleiben.

Die meisten Tests ersetzen die Flugphysik durch ein lineares Ersatzmodell
(Apogäum = Startdruck / 1e4, also 0,1 m bei P_MIN und 100 m bei P_MAX).
Dadurch laufen sie schnell, und Flüge lassen sich zählen. Ersetzt werden
simulate_flight in app.main (Vorabprüfung, Ergebnisflug) und in
app.physics.inverse (Suche, Kontrollflug).

Wenige Tests rechnen mit der echten Physik und prüfen nur Eigenschaften,
keine Zahlenwerte: Die Zielhöhe liegt zwischen den Apogäen bei
p0_gauge ± 1 Pa, und jeder gespeicherte Flug ist aus seinem Kassenbon
reproduzierbar.

Werte frei gewählt, NICHT gemessen.
"""

from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main
import app.physics.inverse as inverse
from app.db import get_session
from app.main import SEARCHER_FACTORIES, app, make_searcher
from app.models import CONFIG_FIELDS, GEOMETRY_FIELDS, Base, Flight, Series, result_values
from app.physics.inverse import P_MAX, P_MIN, P_TOL, STEP0, find_start_pressure
from app.physics.simulation import EXAMPLE_ROCKET, FlightResult, simulate_flight
from app.schemas import DEFAULT_SEARCHER, SEARCHERS, SeriesRead
from app.search.binary_search import BinarySearch
from app.search.exponential_search import ExponentialSearch
from app.search.interpolation_search import InterpolationSearch

GEOMETRY = dict(
    nose_shape="cone", l_nose=0.12, n_fins=3, fin_root_chord=0.10,
    fin_tip_chord=0.05, fin_span=0.08, fin_sweep=0.05, x_fin=0.30,
    x_cg_empty=0.20, l_total=0.42,
)
REQUIRED = {k: v for k, v in asdict(EXAMPLE_ROCKET).items() if k not in GEOMETRY_FIELDS}
MINIMAL = {"name": "Testrakete", **REQUIRED}
FULL = {**MINIMAL, **GEOMETRY}

INVERSE = dict(
    name="Zielhoehen", mode="inverse", param_name="target_apogee",
    param_start=10.0, param_stop=40.0, n_steps=3,
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
    return client.post(f"/api/rockets/{rocket_id}/series", json={**INVERSE, **changes})


def stored_config(flight: Flight):
    return replace(EXAMPLE_ROCKET, **{name: getattr(flight, name) for name in CONFIG_FIELDS})


# --- Lineares Ersatzmodell -------------------------------------------------------

def fake_flight(cfg) -> FlightResult:
    """Streng steigend im Startdruck: 0,1 m bei P_MIN, 100 m bei P_MAX."""
    return FlightResult(
        apogee=cfg.p0_gauge / 1e4, t_apogee=1.0, t_water_end=0.1, t_air_end=0.2,
        v_burnout=10.0, h_burnout=1.0, water_rest=0.0, trajectory=[],
    )


@pytest.fixture
def fake(monkeypatch):
    """Ersetzt die Flugphysik überall und zählt die Flüge."""
    calls = {"n": 0}

    def counted(cfg):
        calls["n"] += 1
        return fake_flight(cfg)

    monkeypatch.setattr(main, "simulate_flight", counted)
    monkeypatch.setattr(inverse, "simulate_flight", counted)
    return calls


@pytest.fixture
def spy(monkeypatch):
    """Zeichnet jeden Aufruf von find_start_pressure im Endpunkt auf."""
    seen = []

    def recording(cfg, target, searcher=None):
        result = find_start_pressure(cfg, target, searcher=searcher)
        seen.append({"target": target, "searcher": searcher, "result": result})
        return result

    monkeypatch.setattr(main, "find_start_pressure", recording)
    return seen


# --- Suchverfahren ---------------------------------------------------------------

def test_every_allowed_searcher_has_a_factory():
    assert tuple(SEARCHER_FACTORIES) == SEARCHERS


@pytest.mark.parametrize("name, cls", [
    ("binary", BinarySearch), ("exponential", ExponentialSearch),
    ("interpolation", InterpolationSearch),
])
def test_make_searcher_returns_the_named_class(name, cls):
    assert type(make_searcher(name)) is cls


def test_exponential_search_uses_the_default_step():
    # Ohne step0 begänne sie mit (hi - lo) / 1024, also anders als der Standard
    assert make_searcher("exponential").step0 == STEP0


def test_interpolation_search_uses_illinois():
    assert make_searcher("interpolation").illinois is True


def test_make_searcher_returns_a_new_instance_each_time():
    assert make_searcher("binary") is not make_searcher("binary")


# --- Erfolgsfall mit Ersatzmodell -------------------------------------------------

def test_inverse_series_returns_201(client, fake):
    response = start_series(client, new_rocket(client))
    assert response.status_code == 201
    body = response.json()
    assert list(body) == list(SeriesRead.model_fields)
    assert body["mode"] == "inverse"
    assert body["param_name"] == "target_apogee"
    assert body["searcher"] == DEFAULT_SEARCHER
    assert body["n_steps"] == 3


def test_default_searcher_is_stored_in_series_and_flights(client, engine, fake):
    body = start_series(client, new_rocket(client)).json()
    with Session(engine) as session:
        assert session.get(Series, body["id"]).searcher == DEFAULT_SEARCHER
    assert {f.searcher for f in flights_of(engine, body["id"])} == {DEFAULT_SEARCHER}


def test_one_flight_per_target(client, engine, fake):
    body = start_series(client, new_rocket(client)).json()
    flights = flights_of(engine, body["id"])
    assert [f.target_apogee for f in flights] == [10.0, 25.0, 40.0]
    assert all(f.series_id == body["id"] for f in flights)


def test_found_pressure_is_stored_as_p0_gauge(client, engine, fake):
    # Ersatzmodell: Zielhöhe h braucht h * 1e4 Pa; Suche auf P_TOL genau
    body = start_series(client, new_rocket(client)).json()
    for f in flights_of(engine, body["id"]):
        assert abs(f.p0_gauge - f.target_apogee * 1e4) <= P_TOL


def test_only_p0_gauge_differs_from_the_rocket(client, engine, fake):
    body = start_series(client, new_rocket(client)).json()
    for f in flights_of(engine, body["id"]):
        for name in CONFIG_FIELDS:
            if name != "p0_gauge":
                assert getattr(f, name) == FULL[name], name


def test_results_come_from_the_result_flight(client, engine, fake):
    body = start_series(client, new_rocket(client)).json()
    for f in flights_of(engine, body["id"]):
        expected = result_values(fake_flight(stored_config(f)))
        assert {k: getattr(f, k) for k in expected} == expected


def test_search_evaluations_are_stored(client, engine, fake, spy):
    body = start_series(client, new_rocket(client)).json()
    flights = flights_of(engine, body["id"])
    assert [f.search_evaluations for f in flights] == [
        s["result"].search_evaluations for s in spy
    ]
    assert all(isinstance(f.search_evaluations, int) for f in flights)


def test_flight_count_is_check_plus_search_plus_control_and_result(client, fake, spy):
    # 2 Flüge Vorabprüfung, dann pro Schritt: Suche + Kontrollflug + Ergebnisflug
    start_series(client, new_rocket(client))
    searched = sum(s["result"].search_evaluations for s in spy)
    assert fake["n"] == 2 + searched + 2 * len(spy)


@pytest.mark.parametrize("name, cls", [
    ("binary", BinarySearch), ("exponential", ExponentialSearch),
    ("interpolation", InterpolationSearch),
])
def test_chosen_searcher_is_used_and_stored(client, engine, fake, spy, name, cls):
    body = start_series(client, new_rocket(client), searcher=name).json()
    assert body["searcher"] == name
    assert all(type(s["searcher"]) is cls for s in spy)
    assert {f.searcher for f in flights_of(engine, body["id"])} == {name}


def test_each_step_gets_a_fresh_searcher(client, fake, spy):
    start_series(client, new_rocket(client))
    assert len({id(s["searcher"]) for s in spy}) == len(spy)


def test_targets_at_the_limits_are_reachable(client, engine, fake):
    # Gleichheit mit den Apogäen bei P_MIN und P_MAX ist erlaubt
    body = start_series(client, new_rocket(client), param_start=0.1, param_stop=100.0,
                        n_steps=2).json()
    assert [f.p0_gauge for f in flights_of(engine, body["id"])] == [P_MIN, P_MAX]


def test_duration_covers_search_not_validation(client, fake, monkeypatch):
    # Gestellte Uhr: jeder Flug dauert 1 s. Die zwei Flüge der Vorabprüfung
    # laufen vor dem Start der Messung.
    monkeypatch.setattr(main, "perf_counter", lambda: float(fake["n"]))
    body = start_series(client, new_rocket(client)).json()
    assert body["duration_s"] == fake["n"] - 2


def test_get_returns_same_inverse_series_as_post(client, fake):
    body = start_series(client, new_rocket(client)).json()
    assert client.get(f"/api/series/{body['id']}").json() == body


def test_rocket_without_geometry_works(client, engine, fake):
    body = start_series(client, new_rocket(client, MINIMAL)).json()
    flights = flights_of(engine, body["id"])
    assert len(flights) == 3
    assert all(getattr(f, name) is None for f in flights for name in GEOMETRY_FIELDS)


# --- Vorabprüfung: unerreichbare Zielhöhe ------------------------------------------

def test_target_too_high_gives_422_before_any_search(client, engine, fake):
    response = start_series(client, new_rocket(client), param_start=50.0, param_stop=200.0)
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 1]  # Werte 50, 125, 200
    assert detail["type"] == "simulation_error"
    assert detail["msg"] == (
        "Schritt 1 (target_apogee = 125.0): "
        f"Zielhöhe liegt über dem Apogäum beim Suchdruck {P_MAX!r} Pa"
    )
    assert fake["n"] == 2  # nur die Vorabprüfung
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


def test_target_too_low_gives_422_before_any_search(client, engine, fake):
    response = start_series(client, new_rocket(client), param_start=0.05, param_stop=50.0)
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 0]
    assert "unter dem Apogäum beim Suchdruck" in detail["msg"]
    assert fake["n"] == 2
    assert count(engine, Series) == 0


def test_failed_check_flight_gives_422(client, engine, monkeypatch):
    def fails(cfg):
        raise RuntimeError("max_steps zu klein")

    rocket_id = new_rocket(client)
    monkeypatch.setattr(main, "simulate_flight", fails)
    response = start_series(client, rocket_id)
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["path", "rocket_id"]
    assert detail["type"] == "simulation_error"
    assert detail["msg"].endswith("max_steps zu klein")
    assert count(engine, Series) == 0


# --- Fehler während der Suche: alles oder nichts ------------------------------------

@pytest.mark.parametrize("error", [ValueError, RuntimeError])
def test_search_error_gives_422_and_stores_nothing(client, engine, fake, monkeypatch, error):
    calls = {"n": 0}

    def fails_at_third_step(cfg, target, searcher=None):
        calls["n"] += 1
        if calls["n"] == 3:
            raise error("target ist bis hi nicht erreichbar.")
        return find_start_pressure(cfg, target, searcher=searcher)

    monkeypatch.setattr(main, "find_start_pressure", fails_at_third_step)
    response = start_series(client, new_rocket(client))
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 2]
    assert detail["type"] == "simulation_error"
    assert detail["msg"] == "Schritt 2 (target_apogee = 40.0): target ist bis hi nicht erreichbar."
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


def test_not_converged_gives_422_and_stores_nothing(client, engine, fake, monkeypatch):
    def not_converged(cfg, target, searcher=None):
        r = find_start_pressure(cfg, target, searcher=searcher)
        return replace(r, width=5.0, converged=False)

    monkeypatch.setattr(main, "find_start_pressure", not_converged)
    response = start_series(client, new_rocket(client))
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 0]
    assert detail["msg"] == (
        f"Schritt 0 (target_apogee = 10.0): Suche nicht konvergiert "
        f"(Restintervall 5.0 Pa > {P_TOL!r} Pa)"
    )
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


def test_result_flight_error_gives_422(client, engine, fake, monkeypatch):
    calls = {"n": 0}

    def fails_after_check(cfg):
        calls["n"] += 1
        if calls["n"] > 2:  # Vorabprüfung gelingt, Ergebnisflug scheitert
            raise ValueError("Wasserphase nicht beendet")
        return fake_flight(cfg)

    monkeypatch.setattr(main, "simulate_flight", fails_after_check)
    response = start_series(client, new_rocket(client))
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 0]
    assert detail["msg"].endswith("Wasserphase nicht beendet")
    assert count(engine, Series) == 0


def test_other_errors_stay_500_and_store_nothing(engine, fake, monkeypatch):
    def broken(cfg, target, searcher=None):
        raise ZeroDivisionError("Programmierfehler")

    try:
        with make_client(engine, raise_server_exceptions=False) as c:
            rocket_id = new_rocket(c)
            monkeypatch.setattr(main, "find_start_pressure", broken)
            assert start_series(c, rocket_id).status_code == 500
    finally:
        app.dependency_overrides.clear()
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


# --- Ungültige Eingaben ------------------------------------------------------------

def test_unknown_rocket_404(client, engine):
    response = start_series(client, 999999)
    assert response.status_code == 404
    assert count(engine, Series) == 0


@pytest.mark.parametrize("changes", [
    {"n_steps": 41}, {"param_name": "p0_gauge"}, {"param_start": 0.0},
    {"searcher": "bisection"},
])
def test_invalid_inverse_body_gives_422_and_stores_nothing(client, engine, changes):
    response = start_series(client, new_rocket(client), **changes)
    assert response.status_code == 422
    assert count(engine, Series) == 0
    assert count(engine, Flight) == 0


# --- Echte Physik (Eigenschaften, keine Zahlenwerte) --------------------------------

@pytest.mark.parametrize("name", SEARCHERS)
def test_real_target_lies_between_neighbouring_pressures(client, engine, name):
    body = start_series(client, new_rocket(client), searcher=name, n_steps=2).json()
    for f in flights_of(engine, body["id"]):
        cfg = stored_config(f)
        below = simulate_flight(replace(cfg, p0_gauge=f.p0_gauge - P_TOL)).apogee
        above = simulate_flight(replace(cfg, p0_gauge=f.p0_gauge + P_TOL)).apogee
        assert below <= f.target_apogee <= above


def test_real_flights_are_reproducible_and_equal_the_control_flight(client, engine, spy):
    body = start_series(client, new_rocket(client), n_steps=2).json()
    flights = flights_of(engine, body["id"])
    for f in flights:
        # Kassenbon: Die gespeicherte Konfiguration ergibt dieselben Ergebnisse
        expected = result_values(simulate_flight(stored_config(f)))
        assert {k: getattr(f, k) for k in expected} == expected
    # Ergebnisflug und Kontrollflug der Suche stimmen überein
    assert [f.p0_gauge for f in flights] == [s["result"].p0_gauge for s in spy]
    assert [f.apogee for f in flights] == [s["result"].apogee for s in spy]


def test_real_unreachable_target_gives_422(client, engine):
    response = start_series(client, new_rocket(client), param_start=1e4, param_stop=1e5,
                            n_steps=2)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "steps", 0]
    assert count(engine, Series) == 0