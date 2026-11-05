"""Tests für FlightRead: Kassenbon eines Flugs.

Vertragstests: FlightRead muss jede Spalte der Tabelle flights enthalten
(sonst fehlte etwas auf dem Kassenbon) und die Ergebnisfelder genau wie
FlightResult benennen (ohne Flugkurve). Die Feldreihenfolge ist auch die
Spaltenreihenfolge des späteren CSV-Exports und wird deshalb fest geprüft.

Werte frei gewählt, NICHT gemessen.
"""

from dataclasses import asdict, fields
from datetime import datetime, timezone

from app.models import CONFIG_FIELDS, Flight, config_values
from app.physics.simulation import EXAMPLE_ROCKET, FlightResult
from app.schemas import FlightRead

RESULT_FIELDS = [f.name for f in fields(FlightResult) if f.name != "trajectory"]
INVERSE_FIELDS = ["target_apogee", "searcher", "search_evaluations"]
HEAD_FIELDS = ["id", "created_at", "rocket_id", "series_id", "model_version"]

RESULT = dict(
    apogee=40.0, t_apogee=2.5, t_water_end=0.05, t_air_end=0.06,
    v_burnout=30.0, h_burnout=1.0, water_rest=0.0,
)


def make_flight(**overrides) -> Flight:
    """Flug-Zeile ohne Datenbank (created_at von Hand, sonst setzt sie PostgreSQL)."""
    values = dict(
        id=7, created_at=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        rocket_id=1, series_id=None, model_version="1",
        **config_values(EXAMPLE_ROCKET), **RESULT,
    )
    values.update(overrides)
    return Flight(**values)


def test_field_order_is_fixed():
    # Reihenfolge = CSV-Spalten: Kopf, Konfiguration, inverser Modus, Ergebnis
    assert list(FlightRead.model_fields) == [
        *HEAD_FIELDS, *CONFIG_FIELDS, *INVERSE_FIELDS, *RESULT_FIELDS,
    ]


def test_every_flight_column_is_on_the_receipt():
    # Neue Spalte in flights ohne Feld in FlightRead -> rot
    assert set(FlightRead.model_fields) == set(Flight.__table__.columns.keys())


def test_result_fields_match_flightresult_without_trajectory():
    assert "trajectory" not in FlightRead.model_fields
    assert set(RESULT_FIELDS) <= set(FlightRead.model_fields)


def test_reads_forward_flight_from_row():
    read = FlightRead.model_validate(make_flight())
    data = read.model_dump()
    assert data["id"] == 7
    assert data["model_version"] == "1"
    assert data["series_id"] is None
    assert all(data[name] is None for name in INVERSE_FIELDS)
    assert {k: data[k] for k in RESULT} == RESULT
    assert {k: data[k] for k in CONFIG_FIELDS} == asdict(EXAMPLE_ROCKET)


def test_reads_inverse_flight_from_row():
    row = make_flight(series_id=3, target_apogee=30.0, searcher="ExponentialSearch",
                      search_evaluations=25)
    data = FlightRead.model_validate(row).model_dump()
    assert (data["series_id"], data["target_apogee"], data["searcher"],
            data["search_evaluations"]) == (3, 30.0, "ExponentialSearch", 25)