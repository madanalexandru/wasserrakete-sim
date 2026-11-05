"""Tests für den CSV-Export (app/export.py), ohne Datenbank und ohne HTTP.

Geprüft wird: Spalten = FlightRead in fester Reihenfolge; Rundreise mit dem
csv-Modul ergibt dieselben Werte wie die JSON-Antwort; volle Genauigkeit;
null -> leeres Feld; created_at wie in der JSON-Antwort; Komma, Punkt,
CRLF; reines ASCII; die Funktion sortiert nicht.

Werte frei gewählt, NICHT gemessen und NICHT gerechnet.
"""

import csv
import io
from dataclasses import replace
from datetime import datetime, timezone

from app.export import CSV_COLUMNS, flights_to_csv
from app.models import Flight, config_values
from app.physics.simulation import EXAMPLE_ROCKET
from app.schemas import FlightRead

RESULT = dict(
    apogee=40.0, t_apogee=2.5, t_water_end=0.05, t_air_end=0.06,
    v_burnout=30.0, h_burnout=1.0, water_rest=0.0,
)

GEOMETRY_ROCKET = replace(
    EXAMPLE_ROCKET,
    nose_shape="ogive", l_nose=0.12, n_fins=4, fin_root_chord=0.10,
    fin_tip_chord=0.05, fin_span=0.08, fin_sweep=0.05, x_fin=0.30,
    x_cg_empty=0.20, l_total=0.42,
)


def make_flight(cfg=EXAMPLE_ROCKET, **overrides) -> Flight:
    """Flug-Zeile ohne Datenbank (created_at von Hand, sonst setzt sie PostgreSQL)."""
    values = dict(
        id=7, created_at=datetime(2026, 11, 5, 12, 0, 1, 234567, tzinfo=timezone.utc),
        rocket_id=1, series_id=3, model_version="1",
        **config_values(cfg), **RESULT,
    )
    values.update(overrides)
    return Flight(**values)


def read_back(text: str) -> list[list[str]]:
    """CSV-Text -> Zeilen als Listen von Strings (wie ein fremdes Programm)."""
    return list(csv.reader(io.StringIO(text, newline="")))


def to_read(row: list[str]) -> FlightRead:
    """Eine CSV-Zeile -> FlightRead; leeres Feld -> null."""
    return FlightRead.model_validate(
        {name: (value if value != "" else None) for name, value in zip(CSV_COLUMNS, row)}
    )


def test_columns_are_flightread_in_order():
    assert CSV_COLUMNS == tuple(FlightRead.model_fields)
    assert len(CSV_COLUMNS) == 33


def test_header_is_field_names_only():
    assert read_back(flights_to_csv([]))[0] == list(CSV_COLUMNS)


def test_no_flights_gives_header_only():
    assert flights_to_csv([]) == ",".join(CSV_COLUMNS) + "\r\n"


def test_one_line_per_flight_with_33_fields():
    rows = read_back(flights_to_csv([make_flight(id=1), make_flight(id=2)]))
    assert len(rows) == 3  # Kopfzeile + 2 Flüge
    assert all(len(row) == 33 for row in rows)


def test_roundtrip_forward_flight_without_geometry():
    flight = make_flight()
    row = read_back(flights_to_csv([flight]))[1]
    assert to_read(row) == FlightRead.model_validate(flight)


def test_roundtrip_with_geometry_and_inverse_fields():
    flight = make_flight(
        GEOMETRY_ROCKET, target_apogee=35.5, searcher="ExponentialSearch",
        search_evaluations=27,
    )
    row = read_back(flights_to_csv([flight]))[1]
    assert to_read(row) == FlightRead.model_validate(flight)


def test_values_equal_json_response():
    # Jede Zelle = Wert der JSON-Antwort als Text; null -> leer
    flight = make_flight(GEOMETRY_ROCKET)
    expected = FlightRead.model_validate(flight).model_dump(mode="json")
    row = read_back(flights_to_csv([flight]))[1]
    for name, cell in zip(CSV_COLUMNS, row):
        value = expected[name]
        assert cell == ("" if value is None else str(value)), name


def test_null_is_empty_field():
    row = dict(zip(CSV_COLUMNS, read_back(flights_to_csv([make_flight(series_id=None)]))[1]))
    for name in ("series_id", "nose_shape", "l_total", "target_apogee",
                 "searcher", "search_evaluations"):
        assert row[name] == "", name


def test_full_precision():
    # Werte, die bei Rundung auf wenige Stellen verloren gingen
    flight = make_flight(apogee=0.1 + 0.2, water_rest=1.234567890123e-7, p0_gauge=487654.3210987654)
    read = to_read(read_back(flights_to_csv([flight]))[1])
    assert read.apogee == 0.1 + 0.2
    assert read.water_rest == 1.234567890123e-7
    assert read.p0_gauge == 487654.3210987654


def test_created_at_like_json_response():
    flight = make_flight()
    row = dict(zip(CSV_COLUMNS, read_back(flights_to_csv([flight]))[1]))
    assert row["created_at"] == "2026-11-05T12:00:01.234567Z"
    assert row["created_at"] == FlightRead.model_validate(flight).model_dump(mode="json")["created_at"]


def test_comma_point_and_crlf():
    text = flights_to_csv([make_flight()])
    lines = text.split("\r\n")
    assert lines[-1] == ""  # letzte Zeile endet mit CRLF
    assert len(lines) == 3
    assert "\n" not in text.replace("\r\n", "")  # kein einzelnes LF
    assert ";" not in text
    assert "0.5" in lines[1].split(",")  # c_w mit Dezimalpunkt


def test_text_is_ascii_without_bom():
    text = flights_to_csv([make_flight(GEOMETRY_ROCKET, searcher="BinarySearch")])
    assert text.isascii()  # wird rot, sobald ein Wert Nicht-ASCII enthält
    assert not text.startswith("\ufeff")


def test_order_is_kept():
    # Die Funktion sortiert nicht; die Reihenfolge kommt von der Abfrage
    flights = [make_flight(id=i) for i in (5, 2, 9)]
    rows = read_back(flights_to_csv(flights))[1:]
    assert [row[0] for row in rows] == ["5", "2", "9"]


def test_accepts_generator():
    rows = read_back(flights_to_csv(make_flight(id=i) for i in range(3)))
    assert len(rows) == 4