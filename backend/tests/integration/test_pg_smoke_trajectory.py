"""Prüfablauf Flugkurve gegen PostgreSQL (Punkte P1-P15).

Übernimmt das frühere Prüfskript als Test: gleiche Punkte, gleiche
Nummern. Statt Bestand vorher/nachher gilt hier: leere Datenbank zu
Beginn der Datei. Werte der Rakete frei gewählt, NICHT gemessen.

Kernpunkt P10: Das Ende der Kurve muss bitgenau dem in PostgreSQL
gespeicherten Apogäum entsprechen. Ergebniswerte werden nie direkt
verglichen, sondern erst in eine Ja/Nein-Variable gelegt, und die
Szenario-Daten liegen in Hidden. Ein Fehlschlag zeigt dann nur
"assert False" und "<Hidden: ...>", keine Ergebniswerte.
"""

import pytest

from pg_setup import Hidden, count_rows

ROCKET = {"name": "Smoke Flugkurve", "v_bottle": 0.0015, "v_water0": 0.0005,
          "p0_gauge": 500000.0, "d_nozzle": 0.022, "m_empty": 0.15,
          "c_w": 0.5, "d_body": 0.09}
CURVE_FIELDS = ["flight_id", "model_version", "t", "h", "v"]


@pytest.fixture(scope="module")
def scenario(pg_module_client, pg_engine):
    client = pg_module_client
    before = count_rows(pg_engine, "rockets", "flights")
    rocket = client.post("/api/rockets", json=ROCKET)
    flight = client.post(f"/api/rockets/{rocket.json()['id']}/flights")
    fid = flight.json()["id"]
    curve = client.get(f"/api/flights/{fid}/trajectory")
    return Hidden({"client": client, "before": before, "rocket": rocket, "flight": flight,
                   "fid": fid, "curve": curve, "body": curve.json()})


def test_p01_empty_before(scenario):
    assert scenario["before"] == (0, 0)


def test_p02_rocket_created(scenario):
    assert scenario["rocket"].status_code == 201
    assert isinstance(scenario["rocket"].json()["id"], int)


def test_p03_flight_created(scenario):
    assert scenario["flight"].status_code == 201
    assert isinstance(scenario["fid"], int)


def test_p04_curve_fields(scenario):
    assert scenario["curve"].status_code == 200
    assert list(scenario["body"]) == CURVE_FIELDS


def test_p05_flight_id_and_model_version(scenario):
    body, flight = scenario["body"], scenario["flight"].json()
    assert body["flight_id"] == scenario["fid"]
    assert body["model_version"] == flight["model_version"]


def test_p06_same_length_2_to_500(scenario):
    t, h, v = (scenario["body"][k] for k in ("t", "h", "v"))
    assert len(t) == len(h) == len(v)
    assert 2 <= len(t) <= 500


def test_p07_response_below_50_kb(scenario):
    assert len(scenario["curve"].content) < 50 * 1024


def test_p08_starts_at_zero(scenario):
    b = scenario["body"]
    at_zero = (b["t"][0], b["h"][0], b["v"][0]) == (0.0, 0.0, 0.0)
    assert at_zero


def test_p09_time_strictly_increasing(scenario):
    t = scenario["body"]["t"]
    increasing = all(a < b for a, b in zip(t, t[1:]))
    assert increasing


def test_p10_end_equals_stored_apogee(scenario):
    b, flight = scenario["body"], scenario["flight"].json()
    stored = scenario["client"].get(f"/api/flights/{scenario['fid']}").json()
    exact = (
        b["h"][-1] == flight["apogee"] == stored["apogee"]
        and b["t"][-1] == flight["t_apogee"] == stored["t_apogee"]
        and b["v"][-1] == 0.0
    )
    assert exact


def test_p11_second_call_identical(scenario):
    again = scenario["client"].get(f"/api/flights/{scenario['fid']}/trajectory")
    identical = again.status_code == 200 and again.content == scenario["curve"].content
    assert identical


def test_p12_flight_get_equals_post_without_curve(scenario):
    got = scenario["client"].get(f"/api/flights/{scenario['fid']}")
    same = got.status_code == 200 and got.json() == scenario["flight"].json()
    assert same
    assert "trajectory" not in got.json()


def test_p13_unknown_flight(scenario):
    response = scenario["client"].get("/api/flights/999999/trajectory")
    assert response.status_code == 404
    assert response.json() == {"detail": "Flug nicht gefunden"}


def test_p14_not_a_number(scenario):
    assert scenario["client"].get("/api/flights/abc/trajectory").status_code == 422


def test_p15_exactly_one_rocket_and_one_flight(scenario, pg_engine):
    assert count_rows(pg_engine, "rockets", "flights") == (1, 1)