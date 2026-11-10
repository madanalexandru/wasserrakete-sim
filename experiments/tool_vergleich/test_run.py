"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -m unittest discover -s tool_vergleich -v
"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import run

# Erwartete Raketen, unabhängig von run.py abgeschrieben aus dem c_w-Plan.
EXPECTED = {
    "R0": {},
    "R1": {"p0_gauge": 3e5},
    "R2": {"p0_gauge": 7e5},
    "R3": {"v_water0": 0.3e-3},
    "R4": {"v_water0": 0.7e-3},
    "R5": {"d_nozzle": 0.015},
    "R6": {"m_empty": 0.10},
    "R7": {"m_empty": 0.25},
    "R8": {"v_bottle": 1.0e-3, "d_body": 0.079},
    "R9": {"v_bottle": 2.0e-3, "d_body": 0.102},
}
EXPECTED_BASE = {
    "v_bottle": 1.5e-3, "v_water0": 0.5e-3, "p0_gauge": 5e5, "d_nozzle": 0.022,
    "m_empty": 0.15, "c_w": 0.345 * 1.2039 / 1.225, "d_body": 0.09,
}
KENNZAHLEN = (Path(__file__).resolve().parent.parent
              / "cw_sensitivitaet" / "results" / "kennzahlen.csv")
SECRET_APOGEE = 12.3456789  # Testwert; darf nie ausgegeben werden


def fake_flight(fid, rid, config, **override):
    """JSON wie FlightRead, nur mit den geprüften Feldern."""
    flight = {"id": fid, "rocket_id": rid, "series_id": None,
              "model_version": "1", **config, "temp0": 293.15,
              "apogee": SECRET_APOGEE}
    flight.update(override)
    return json.dumps(flight).encode("utf-8")


class RocketSet(unittest.TestCase):
    def test_labels_in_order(self):
        self.assertEqual([label for label, _ in run.rockets()],
                         [f"R{i}" for i in range(10)])

    def test_base(self):
        self.assertEqual(run.BASE, EXPECTED_BASE)

    def test_each_rocket_differs_only_in_planned_fields(self):
        for label, config in run.rockets():
            with self.subTest(label=label):
                self.assertEqual(config, {**EXPECTED_BASE, **EXPECTED[label]})

    def test_cw_strich_equals_kennzahlen(self):
        with open(KENNZAHLEN, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 10)
        for row in rows:
            with self.subTest(label=row["label"]):
                self.assertEqual(float(row["cw_strich"]), run.CW_STRICH)

    def test_no_temperature_and_no_geometry_sent(self):
        for label, config in run.rockets():
            payload = run.rocket_payload(label, config)
            self.assertEqual(set(payload), set(EXPECTED_BASE) | {"name"})

    def test_names_are_ascii(self):
        for label, config in run.rockets():
            self.assertTrue(run.rocket_payload(label, config)["name"].isascii())


class CheckFlight(unittest.TestCase):
    config = {**EXPECTED_BASE}

    def check(self, **override):
        return run.check_flight(fake_flight(7, 3, self.config, **override),
                                "R0", 3, self.config)

    def test_valid_flight_passes(self):
        self.assertEqual(self.check(), 7)

    def test_wrong_rocket_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(rocket_id=4)

    def test_series_flight_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(series_id=5)

    def test_other_model_version_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(model_version="2")

    def test_changed_cw_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(c_w=0.345)

    def test_other_temperature_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(temp0=298.15)

    def test_missing_apogee_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(apogee=None)

    def test_error_text_contains_no_values(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.check(c_w=0.345)
        self.assertNotIn("0.345", str(ctx.exception))
        self.assertNotIn(str(SECRET_APOGEE), str(ctx.exception))


class Measure(unittest.TestCase):
    def fake_api(self):
        """Antwortet wie die API: Rakete i bekommt ID 100+i, Flug ID 200+i."""
        state = {"configs": {}}

        def request(method, path, payload=None, timeout=60):
            if method == "POST" and path == "/rockets":
                rid = 100 + len(state["configs"])
                state["configs"][rid] = {k: v for k, v in payload.items() if k != "name"}
                return 201, json.dumps({"id": rid}).encode("utf-8")
            rid = int(path.split("/")[2])
            return 201, fake_flight(rid + 100, rid, state["configs"][rid])

        return request

    def test_ten_flights_and_no_apogee_printed(self):
        out = io.StringIO()
        with mock.patch.object(run, "request", side_effect=self.fake_api()), \
                redirect_stdout(out):
            results = run.measure()
        self.assertEqual([r["label"] for r in results], [f"R{i}" for i in range(10)])
        self.assertEqual(results[0]["file"], "modell_R0_flug_200.json")
        self.assertNotIn(str(SECRET_APOGEE), out.getvalue())

    def test_flight_post_has_no_body(self):
        calls = []
        api = self.fake_api()

        def spy(method, path, payload=None, timeout=60):
            calls.append((method, path, payload))
            return api(method, path, payload, timeout)

        with mock.patch.object(run, "request", side_effect=spy), \
                mock.patch("builtins.print"):
            run.measure()
        flights = [c for c in calls if c[1].endswith("/flights")]
        self.assertEqual(len(flights), 10)
        self.assertTrue(all(c[0] == "POST" and c[2] is None for c in flights))


class Writing(unittest.TestCase):
    def results(self):
        return [{"label": "R0", "rocket_id": 11, "flight_id": 21,
                 "file": "modell_R0_flug_21.json", "json": b'{"id":21}'}]

    def test_json_written_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            run.write_results(self.results(), data)
            self.assertEqual((data / "modell_R0_flug_21.json").read_bytes(), b'{"id":21}')

    def test_manifest_without_json_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            run.write_results(self.results(), data)
            raw = (data / "modell_manifest.csv").read_bytes()
            self.assertEqual(raw, b"label,rocket_id,flight_id,file\r\n"
                                  b"R0,11,21,modell_R0_flug_21.json\r\n")

    def test_existing_tool_files_do_not_block_and_stay_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "tool_werte.csv").write_bytes(b"alt\r\n")
            with mock.patch.object(run, "wait_for_api"), \
                    mock.patch.object(run, "request", side_effect=Measure().fake_api()), \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 0)
            self.assertEqual((data / "tool_werte.csv").read_bytes(), b"alt\r\n")
            self.assertEqual(len(list(data.glob("modell_R*_flug_*.json"))), 10)

    def test_existing_manifest_aborts_without_contacting_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "modell_manifest.csv").write_text("alt", encoding="utf-8")
            with mock.patch.object(run, "request") as req, \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 2)
            req.assert_not_called()

    def test_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            with mock.patch.object(run, "wait_for_api"), \
                    mock.patch.object(run, "request", return_value=(422, b"{}")), \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 1)
            self.assertEqual(list(data.iterdir()), [])


if __name__ == "__main__":
    unittest.main()