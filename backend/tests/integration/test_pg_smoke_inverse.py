"""Prüfablauf inverse Serie gegen PostgreSQL (Punkte 1-24).

Übernimmt das frühere Prüfskript als Test: gleiche Punkte, gleiche
Nummern. Statt Bestand vorher/nachher gilt hier: leere Datenbank zu
Beginn der Datei, daher erwartet Punkt 2 (0, 0). Werte der Rakete und
Zielhöhen frei gewählt, NICHT gemessen.

Gefundene Startdrücke, Apogäen und search_evaluations werden nie direkt
verglichen, sondern erst in eine Ja/Nein-Variable gelegt, und die
Szenario-Daten liegen in Hidden. Ein Fehlschlag zeigt dann nur
"assert False" und "<Hidden: ...>", keine Ergebniswerte. Zielhöhen sind Eingaben.
"""

import csv
import io

import pytest

from app.models import CONFIG_FIELDS
from app.physics.simulation import MODEL_VERSION
from app.schemas import FlightRead
from pg_setup import Hidden, count_rows

ROCKET = {"name": "Smoke-Test Invers", "v_bottle": 2.0e-3, "v_water0": 6.0e-4,
          "p0_gauge": 4.0e5, "d_nozzle": 0.021, "m_empty": 0.18, "c_w": 0.45,
          "d_body": 0.1}
INVERSE = {"name": "Smoke invers", "mode": "inverse", "param_name": "target_apogee",
           "param_start": 15.0, "param_stop": 35.0, "n_steps": 3}


def csv_rows(client, series_id):
    response = client.get(f"/api/series/{series_id}/flights.csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"), newline="")))
    return response, rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def counts(engine):
    return count_rows(engine, "series", "flights")


@pytest.fixture(scope="module")
def scenario(pg_module_client, pg_engine):
    """Rakete und inverse Serie mit dem Standardverfahren."""
    client = pg_module_client
    rocket = client.post("/api/rockets", json=ROCKET)
    rid = rocket.json()["id"]
    before = counts(pg_engine)
    post = client.post(f"/api/rockets/{rid}/series", json=INVERSE)
    sid = post.json().get("id")
    response, header, rows = csv_rows(client, sid)
    return Hidden({"client": client, "rocket": rocket, "rid": rid, "before": before,
                   "post": post, "sid": sid, "csv": response, "header": header, "rows": rows})


@pytest.fixture(scope="module")
def other_searchers(scenario):
    """Je eine kleine Serie mit binärer Suche und Interpolationssuche."""
    client, rid = scenario["client"], scenario["rid"]
    result = Hidden()
    for name in ("binary", "interpolation"):
        post = client.post(f"/api/rockets/{rid}/series",
                           json={**INVERSE, "n_steps": 2, "searcher": name})
        found = ({r["searcher"] for r in csv_rows(client, post.json()["id"])[2]}
                 if post.status_code == 201 else None)
        result[name] = (post, found)
    return result


@pytest.fixture(scope="module")
def failures(scenario, other_searchers, pg_engine):
    """Abgewiesene Anfragen, Bestand direkt davor und danach."""
    client, rid = scenario["client"], scenario["rid"]
    mid = counts(pg_engine)
    unreachable = client.post(f"/api/rockets/{rid}/series",
                              json={**INVERSE, "param_start": 1e4, "param_stop": 2e4,
                                    "n_steps": 2})
    bad = [
        {**INVERSE, "n_steps": 41},
        {**INVERSE, "param_name": "p0_gauge"},
        {**INVERSE, "mode": "forward", "param_name": "p0_gauge", "param_start": 2e5,
         "param_stop": 3e5, "searcher": "binary"},
    ]
    bad_status = [client.post(f"/api/rockets/{rid}/series", json=b).status_code for b in bad]
    return Hidden({"mid": mid, "unreachable": unreachable, "bad_status": bad_status,
                   "after": counts(pg_engine)})


def test_01_rocket_created(scenario):
    assert scenario["rocket"].status_code == 201
    assert isinstance(scenario["rid"], int)


def test_02_empty_before(scenario):
    assert scenario["before"] == (0, 0)


def test_03_series_created(scenario):
    post = scenario["post"]
    assert post.status_code == 201
    body = post.json()
    assert (body["mode"], body["param_name"], body["searcher"], body["n_steps"]) == (
        "inverse", "target_apogee", "exponential", 3)


def test_04_duration_positive(scenario):
    assert (scenario["post"].json().get("duration_s") or 0) > 0


def test_05_get_equals_post(scenario):
    got = scenario["client"].get(f"/api/series/{scenario['sid']}").json()
    assert got == scenario["post"].json()


def test_06_csv_response(scenario):
    assert scenario["csv"].status_code == 200
    assert scenario["csv"].headers["content-type"] == "text/csv; charset=utf-8"


def test_07_header_is_flightread(scenario):
    assert scenario["header"] == list(FlightRead.model_fields)
    assert len(scenario["header"]) == 33


def test_08_rows(scenario):
    assert len(scenario["rows"]) == 3


def test_09_only_this_series(scenario):
    assert {r["series_id"] for r in scenario["rows"]} == {str(scenario["sid"])}


def test_10_target_apogee(scenario):
    assert [float(r["target_apogee"]) for r in scenario["rows"]] == [15.0, 25.0, 35.0]


def test_11_searcher(scenario):
    assert {r["searcher"] for r in scenario["rows"]} == {"exponential"}


def test_12_search_evaluations_positive_integer(scenario):
    ok = all(r["search_evaluations"].isdigit() and int(r["search_evaluations"]) > 0
             for r in scenario["rows"])
    assert ok


def test_13_found_pressure_within_search_range(scenario):
    ok = all(1e3 <= float(r["p0_gauge"]) <= 1e6 for r in scenario["rows"])
    assert ok


def test_14_other_configuration_as_rocket(scenario):
    rocket = scenario["rocket"].json()
    same = all(float(r[f]) == float(rocket[f]) if rocket[f] is not None else r[f] == ""
               for r in scenario["rows"] for f in CONFIG_FIELDS if f != "p0_gauge")
    assert same


def test_15_model_version(scenario):
    assert {r["model_version"] for r in scenario["rows"]} == {MODEL_VERSION}


def test_16_each_row_equals_single_flight_json(scenario):
    client = scenario["client"]
    same = all(
        FlightRead.model_validate({k: (v if v != "" else None) for k, v in r.items()})
        == FlightRead.model_validate(client.get(f"/api/flights/{r['id']}").json())
        for r in scenario["rows"]
    )
    assert same


def test_17_created_at_with_z(scenario):
    assert all(r["created_at"].endswith("Z") for r in scenario["rows"])


def test_18_apogee_positive(scenario):
    positive = all(float(r["apogee"]) > 0 for r in scenario["rows"])
    assert positive


@pytest.mark.parametrize("name", ["binary", "interpolation"])
def test_19_20_other_searchers(other_searchers, name):
    post, found = other_searchers[name]
    assert post.status_code == 201
    assert post.json()["searcher"] == name
    assert found == {name}


def test_21_unreachable_target(failures):
    response = failures["unreachable"]
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "steps", 0]
    assert detail["type"] == "simulation_error"
    # Die Meldung nennt nur den Suchdruck, kein Apogäum.
    assert "über dem Apogäum beim Suchdruck 1000000.0 Pa" in detail["msg"]


def test_22_invalid_bodies(failures):
    assert failures["bad_status"] == [422, 422, 422]


def test_23_rejected_requests_write_nothing(failures):
    assert failures["after"] == failures["mid"]


def test_24_new_series_and_flights_in_total(scenario, failures):
    before, after = scenario["before"], failures["after"]
    assert (after[0] - before[0], after[1] - before[1]) == (3, 7)