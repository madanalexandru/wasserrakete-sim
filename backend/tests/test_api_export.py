"""API-Tests: CSV-Export einer Serie (GET /api/series/{id}/flights.csv).

Wie test_api_series.py gegen SQLite im Arbeitsspeicher; die Fixtures sind
bewusst kopiert statt importiert, damit die Dateien unabhängig bleiben.

Geprüft wird: Statuscode, Content-Type und Dateiname; eine Zeile pro Flug,
nur Flüge dieser Serie; jede Zeile = JSON-Antwort des Einzelflugs; Werte
exakt wie in der Datenbank; Sortierung nach dem variierten Parameter statt
nach id; reines ASCII ohne BOM; der Export rechnet und schreibt nichts;
unbekannte ID -> 404, keine Zahl -> 422.

Für die Sortierung werden Zeilen direkt in die Datenbank geschrieben, damit
die IDs absichtlich nicht in Schrittfolge liegen (über die API nicht
herstellbar).

Nicht getestet: id als zweiter Sortierschlüssel bei gleichem Wert des
variierten Parameters. SQLite liefert gleiche Werte ohnehin in der
Reihenfolge der IDs, ein Test bliebe auch ohne die Regel grün. Über die
API kommt Gleichstand nicht vor, weil die Werte einer Serie streng steigen.

Werte frei gewählt, NICHT gemessen.
"""

import csv
import io
from dataclasses import asdict
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main
from app.db import get_session
from app.export import CSV_COLUMNS
from app.main import app
from app.models import GEOMETRY_FIELDS, Base, Flight, Rocket, Series, config_values
from app.physics.simulation import EXAMPLE_ROCKET
from app.schemas import FlightRead

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

RESULT = dict(
    apogee=40.0, t_apogee=2.5, t_water_end=0.05, t_air_end=0.06,
    v_burnout=30.0, h_burnout=1.0, water_rest=0.0,
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


def new_rocket(client, payload=FULL) -> int:
    response = client.post("/api/rockets", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def start_series(client, rocket_id: int, **changes) -> int:
    response = client.post(f"/api/rockets/{rocket_id}/series", json={**SERIES, **changes})
    assert response.status_code == 201
    return response.json()["id"]


def export(client, series_id):
    return client.get(f"/api/series/{series_id}/flights.csv")


def rows_of(response) -> list[dict]:
    """CSV-Antwort -> Zeilen als dict (Spaltenname -> Text), ohne Kopfzeile."""
    rows = list(csv.reader(io.StringIO(response.text, newline="")))
    assert rows[0] == list(CSV_COLUMNS)
    return [dict(zip(CSV_COLUMNS, row)) for row in rows[1:]]


def to_read(row: dict) -> FlightRead:
    """Eine CSV-Zeile -> FlightRead; leeres Feld -> null."""
    return FlightRead.model_validate({k: (v if v != "" else None) for k, v in row.items()})


def insert_series(engine, param_name: str, values: list[float]) -> int:
    """Serie direkt in die Datenbank schreiben; Flüge in der Reihenfolge von values.

    So lassen sich IDs erzeugen, die nicht in Schrittfolge liegen.
    """
    with Session(engine) as session:
        rocket = Rocket(name="Direkt", **config_values(EXAMPLE_ROCKET))
        session.add(rocket)
        session.flush()
        series = Series(
            name="Direkt", rocket_id=rocket.id, mode="forward", param_name=param_name,
            param_start=min(values, default=0.0), param_stop=max(values, default=0.0),
            n_steps=len(values),
        )
        session.add(series)
        session.flush()
        for value in values:
            cfg = {**config_values(EXAMPLE_ROCKET), param_name: value}
            session.add(Flight(
                rocket_id=rocket.id, series_id=series.id, model_version="1",
                created_at=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
                **cfg, **RESULT,
            ))
            session.flush()  # eine ID pro Flug, in der Reihenfolge von values
        session.commit()
        return series.id


# --- Erfolgsfall -------------------------------------------------------------

def test_export_returns_200_csv_as_download(client):
    series_id = start_series(client, new_rocket(client))
    response = export(client, series_id)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="serie_{series_id}.csv"'
    )


def test_one_row_per_flight(client, engine):
    series_id = start_series(client, new_rocket(client), n_steps=4)
    rows = rows_of(export(client, series_id))
    assert len(rows) == 4
    assert {row["series_id"] for row in rows} == {str(series_id)}


def test_only_flights_of_this_series(client):
    rocket_id = new_rocket(client)
    first = start_series(client, rocket_id)
    second = start_series(client, rocket_id, n_steps=5)
    client.post(f"/api/rockets/{rocket_id}/flights")  # Einzelflug ohne Serie
    rows = rows_of(export(client, first))
    assert len(rows) == 3
    assert {row["series_id"] for row in rows} == {str(first)}
    assert len(rows_of(export(client, second))) == 5


def test_each_row_equals_single_flight_json(client):
    series_id = start_series(client, new_rocket(client))
    for row in rows_of(export(client, series_id)):
        single = client.get(f"/api/flights/{row['id']}").json()
        assert to_read(row) == FlightRead.model_validate(single)


def test_values_exactly_as_stored(client, engine):
    series_id = start_series(client, new_rocket(client), param_name="c_w",
                             param_start=0.3, param_stop=0.7)
    rows = rows_of(export(client, series_id))
    with Session(engine) as session:
        for row in rows:
            stored = FlightRead.model_validate(session.get(Flight, int(row["id"])))
            assert to_read(row) == stored


def test_varied_param_from_start_to_exact_stop(client):
    series_id = start_series(client, new_rocket(client), param_start=2e5,
                             param_stop=5e5, n_steps=7)
    values = [float(row["p0_gauge"]) for row in rows_of(export(client, series_id))]
    assert values[0] == 2e5
    assert values[-1] == 5e5
    assert values == sorted(values)


def test_rocket_without_geometry_gives_empty_fields(client):
    series_id = start_series(client, new_rocket(client, MINIMAL))
    for row in rows_of(export(client, series_id)):
        assert all(row[name] == "" for name in GEOMETRY_FIELDS)
        assert row["target_apogee"] == row["searcher"] == row["search_evaluations"] == ""


def test_body_is_ascii_without_bom(client):
    series_id = start_series(client, new_rocket(client))
    body = export(client, series_id).content
    assert body.isascii()
    assert not body.startswith(b"\xef\xbb\xbf")


# --- Sortierung --------------------------------------------------------------

def test_sorted_by_varied_param_not_by_id(client, engine):
    # IDs absichtlich gegen die Schrittfolge: höchster Druck hat die kleinste ID
    series_id = insert_series(engine, "p0_gauge", [6e5, 4e5, 2e5])
    rows = rows_of(export(client, series_id))
    assert [float(row["p0_gauge"]) for row in rows] == [2e5, 4e5, 6e5]
    ids = [int(row["id"]) for row in rows]
    assert ids == sorted(ids, reverse=True)


def test_sorted_by_other_param(client, engine):
    series_id = insert_series(engine, "c_w", [0.7, 0.3, 0.5])
    rows = rows_of(export(client, series_id))
    assert [float(row["c_w"]) for row in rows] == [0.3, 0.5, 0.7]


def test_series_without_flights_gives_header_only(client, engine):
    series_id = insert_series(engine, "p0_gauge", [])
    response = export(client, series_id)
    assert response.status_code == 200
    assert response.text == ",".join(CSV_COLUMNS) + "\r\n"


# --- Nur lesen ---------------------------------------------------------------

def test_export_does_not_compute_or_store(client, engine, monkeypatch):
    series_id = start_series(client, new_rocket(client))
    n_flights, n_series = count(engine, Flight), count(engine, Series)

    def must_not_run(*args, **kwargs):
        raise AssertionError("Der Export darf nicht rechnen")

    monkeypatch.setattr(main, "simulate_flight", must_not_run)
    assert export(client, series_id).status_code == 200
    assert export(client, series_id).text == export(client, series_id).text
    assert count(engine, Flight) == n_flights
    assert count(engine, Series) == n_series


# --- Fehlerfälle -------------------------------------------------------------

@pytest.mark.parametrize("series_id", [999, 0, -1])
def test_unknown_series_404(client, series_id):
    response = export(client, series_id)
    assert response.status_code == 404
    assert response.json() == {"detail": "Serie nicht gefunden"}
    assert response.headers["content-type"] == "application/json"


def test_series_id_must_be_integer(client):
    assert export(client, "abc").status_code == 422