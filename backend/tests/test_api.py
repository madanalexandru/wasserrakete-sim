"""API-Tests: Rakete anlegen (POST) und abrufen (GET).

Die Tests laufen gegen SQLite im Arbeitsspeicher, nicht gegen PostgreSQL
(Entscheidung 1C, Chat 02.11.2026). FastAPI ersetzt dafür get_session
durch eine SQLite-Session (dependency_overrides). Integrationstests gegen
das echte PostgreSQL folgen in einem eigenen Schritt.

StaticPool + check_same_thread=False: Eine SQLite-Datenbank im Speicher
lebt nur in ihrer Verbindung. TestClient ruft die App aus einem anderen
Thread auf; so sehen Test und App dieselbe Verbindung und dieselben Daten.

Werte frei gewählt (wie test_stability.py), NICHT gemessen.

Stabilitätswerte und Sicherheitsnetz (Chat Teil 4, 02.11.2026): Die Tests
für das Netz ersetzen stability_values in app.main per monkeypatch, weil
gültige Eingaben das Netz nach Entscheidung 9x nicht mehr erreichen. Das
Schema benutzt seine eigene Referenz (app.schemas) und bleibt unberührt.
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
from app.physics.stability import stability_values
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


# --- Stabilitätswerte (Entscheidungen 3B, 7a, 8i) -------------------------

def test_create_returns_stability_values(client):
    body = client.post("/api/rockets", json=FULL).json()
    expected = asdict(stability_values(RocketCreate(**FULL).to_config()))
    assert body["stability"] == expected


def test_stability_has_no_judgement(client):
    stability = client.post("/api/rockets", json=FULL).json()["stability"]
    assert set(stability) == {"x_cp", "x_cg_start", "x_cg_empty", "margin_start", "margin_empty"}


def test_create_without_geometry_has_no_stability(client):
    assert client.post("/api/rockets", json=MINIMAL).json()["stability"] is None


def test_get_returns_stability(client):
    created = client.post("/api/rockets", json=FULL).json()
    body = client.get(f"/api/rockets/{created['id']}").json()
    assert body["stability"] == created["stability"]


def test_get_without_geometry_has_no_stability(client):
    created = client.post("/api/rockets", json=MINIMAL).json()
    assert client.get(f"/api/rockets/{created['id']}").json()["stability"] is None


def test_stability_is_not_stored():
    assert "stability" not in Rocket.__table__.columns
    assert not any(c.startswith(("x_cp", "margin")) for c in Rocket.__table__.columns.keys())


# --- Extreme Werte: 422 schon bei der Eingabeprüfung (Entscheidung 9x) -----

@pytest.mark.parametrize("changes", [
    {"fin_sweep": 1e200},                       # vorher ZeroDivisionError
    {"d_body": 1e-200, "d_nozzle": 1e-201},     # vorher 500 (Sandbox 02.11.)
    {"fin_span": 1e200},                        # NaN
])
def test_absurd_values_return_422_and_store_nothing(client, engine, changes):
    response = client.post("/api/rockets", json={**FULL, **changes})
    assert response.status_code == 422
    assert "nicht berechenbar" in response.json()["detail"][0]["msg"]
    assert count_rockets(engine) == 0


# --- Sicherheitsnetz im POST (Entscheidungen 9x, 10β) ---------------------

def raise_value_error(cfg):
    raise ValueError("Testfehler aus der Physik")


def raise_runtime_error(cfg):
    raise RuntimeError("simulierter Programmierfehler")


def test_safety_net_turns_value_error_into_422(client, engine, monkeypatch):
    monkeypatch.setattr("app.main.stability_values", raise_value_error)
    response = client.post("/api/rockets", json=FULL)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["msg"] == "Testfehler aus der Physik"
    assert detail[0]["type"] == "value_error"
    assert count_rockets(engine) == 0  # gerechnet wird vor dem Speichern


def test_safety_net_does_not_hide_other_errors(client, engine, monkeypatch):
    # Kein Netz für alles: ein Programmierfehler bleibt ein Fehler (500)
    monkeypatch.setattr("app.main.stability_values", raise_runtime_error)
    with pytest.raises(RuntimeError):
        client.post("/api/rockets", json=FULL)
    assert count_rockets(engine) == 0


def test_without_geometry_physics_is_not_called(client, monkeypatch):
    monkeypatch.setattr("app.main.stability_values", raise_value_error)
    assert client.post("/api/rockets", json=MINIMAL).status_code == 201


def test_get_has_no_safety_net(client, monkeypatch):
    # Entscheidung 10β: Fehler in gespeicherten Daten -> 500, nicht 422
    rocket_id = client.post("/api/rockets", json=FULL).json()["id"]
    monkeypatch.setattr("app.main.stability_values", raise_value_error)
    with pytest.raises(ValueError):
        client.get(f"/api/rockets/{rocket_id}")


def test_get_server_error_status_is_500(engine, monkeypatch):
    # Wie der Client es sieht: Statuscode 500 statt Ausnahme im Test
    def sqlite_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sqlite_session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            rocket_id = c.post("/api/rockets", json=FULL).json()["id"]
            monkeypatch.setattr("app.main.stability_values", raise_value_error)
            assert c.get(f"/api/rockets/{rocket_id}").status_code == 500
    finally:
        app.dependency_overrides.clear()