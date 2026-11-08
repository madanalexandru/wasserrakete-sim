"""Prüfablauf CSV-Export einer Vorwärtsserie gegen PostgreSQL (Punkte 01-17).

Übernimmt das frühere Prüfskript als Test: gleiche Punkte, gleiche
Nummern. Statt Bestand vorher/nachher gilt hier: leere Datenbank zu
Beginn der Datei. Werte der Rakete frei gewählt, NICHT gemessen.

Ergebniswerte (Apogäen usw.) werden nie direkt verglichen, sondern erst
in eine Ja/Nein-Variable gelegt, und die Szenario-Daten liegen in Hidden.
Ein Fehlschlag zeigt dann nur "assert False" und "<Hidden: ...>", keine
Ergebniswerte.
"""

import csv
import io

import pytest

from app.export import CSV_COLUMNS
from app.schemas import FlightRead
from pg_setup import Hidden, count_rows

ROCKET = {"name": "Smoke CSV", "v_bottle": 0.0015, "v_water0": 0.0005,
          "p0_gauge": 500000.0, "d_nozzle": 0.022, "m_empty": 0.15,
          "c_w": 0.5, "d_body": 0.09}
SERIES = {"name": "Smoke CSV vorwaerts", "mode": "forward", "param_name": "p0_gauge",
          "param_start": 300000.0, "param_stop": 500000.0, "n_steps": 5}


@pytest.fixture(scope="module")
def scenario(pg_module_client, pg_engine):
    """Rakete, Serie und ein Einzelflug, der nicht in der CSV stehen darf."""
    client = pg_module_client
    rid = client.post("/api/rockets", json=ROCKET).json()["id"]
    series = client.post(f"/api/rockets/{rid}/series", json=SERIES)
    assert series.status_code == 201
    single = client.post(f"/api/rockets/{rid}/flights")
    assert single.status_code == 201
    sid = series.json()["id"]
    before = count_rows(pg_engine, "rockets", "series", "flights")
    response = client.get(f"/api/series/{sid}/flights.csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"), newline="")))
    data = [dict(zip(CSV_COLUMNS, r)) for r in rows[1:]]
    return Hidden({"client": client, "sid": sid, "series": series.json(), "before": before,
                   "response": response, "rows": rows, "data": data})


def values_of(scenario):
    return [float(r[SERIES["param_name"]]) for r in scenario["data"]]


def test_p01_status(scenario):
    assert scenario["response"].status_code == 200


def test_p02_content_type(scenario):
    assert scenario["response"].headers["content-type"] == "text/csv; charset=utf-8"


def test_p03_content_disposition(scenario):
    expected = f'attachment; filename="serie_{scenario["sid"]}.csv"'
    assert scenario["response"].headers["content-disposition"] == expected


def test_p04_ascii_without_bom(scenario):
    body = scenario["response"].content
    assert body.isascii() and not body.startswith(b"\xef\xbb\xbf")


def test_p05_header_is_flightread(scenario):
    assert scenario["rows"][0] == list(CSV_COLUMNS)
    assert len(scenario["rows"][0]) == 33


def test_p06_rows_and_fields(scenario):
    assert len(scenario["data"]) == SERIES["n_steps"]
    assert {len(r) for r in scenario["rows"]} == {33}


def test_p07_only_this_series(scenario):
    # Der Einzelflug derselben Rakete erscheint nicht.
    assert {r["series_id"] for r in scenario["data"]} == {str(scenario["sid"])}


def test_p08_varied_parameter(scenario):
    assert scenario["series"]["param_name"] == "p0_gauge"
    assert values_of(scenario) == [300000.0, 350000.0, 400000.0, 450000.0, 500000.0]


def test_p09_strictly_increasing(scenario):
    values = values_of(scenario)
    assert all(a < b for a, b in zip(values, values[1:]))


def test_p10_start_and_stop_exact(scenario):
    values = values_of(scenario)
    assert values[0] == scenario["series"]["param_start"]
    assert values[-1] == scenario["series"]["param_stop"]


def test_p11_each_row_equals_single_flight_json(scenario):
    client = scenario["client"]
    same = all(
        FlightRead.model_validate({k: (v if v != "" else None) for k, v in r.items()})
        == FlightRead.model_validate(client.get(f"/api/flights/{r['id']}").json())
        for r in scenario["data"]
    )
    assert same


def test_p12_created_at_with_z(scenario):
    assert all(r["created_at"].endswith("Z") for r in scenario["data"])


def test_p13_apogee_positive(scenario):
    positive = all(float(r["apogee"]) > 0 for r in scenario["data"])
    assert positive


def test_p14_second_export_identical(scenario):
    again = scenario["client"].get(f"/api/series/{scenario['sid']}/flights.csv")
    identical = again.content == scenario["response"].content
    assert identical


def test_p15_export_writes_nothing(scenario, pg_engine):
    scenario["client"].get(f"/api/series/{scenario['sid']}/flights.csv")
    assert count_rows(pg_engine, "rockets", "series", "flights") == scenario["before"]


def test_p16_unknown_series(scenario):
    response = scenario["client"].get("/api/series/999999/flights.csv")
    assert response.status_code == 404
    assert response.json() == {"detail": "Serie nicht gefunden"}


def test_p17_not_a_number(scenario):
    assert scenario["client"].get("/api/series/abc/flights.csv").status_code == 422