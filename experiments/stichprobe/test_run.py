"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Zwei Tests laden parameterstudie/run.py und tool_vergleich/run.py, um Stufen
und c_w' zu vergleichen (keine Ausgabe).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -m unittest discover -s stichprobe -v
"""

import csv
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import run

# Erwartete Eckraketen, unabhängig von run.py abgeschrieben aus der Vorab-Notiz.
EXPECTED = {
    "E1": {"v_bottle": 1.0e-3, "v_water0": 0.33e-3, "p0_gauge": 7e5,
           "d_nozzle": 0.022, "m_empty": 0.10, "d_body": 0.079},
    "E2": {"v_bottle": 1.0e-3, "v_water0": 0.33e-3, "p0_gauge": 3e5,
           "d_nozzle": 0.015, "m_empty": 0.25, "d_body": 0.079},
    "E3": {"v_bottle": 2.0e-3, "v_water0": 0.66e-3, "p0_gauge": 7e5,
           "d_nozzle": 0.022, "m_empty": 0.10, "d_body": 0.102},
    "E4": {"v_bottle": 2.0e-3, "v_water0": 0.66e-3, "p0_gauge": 3e5,
           "d_nozzle": 0.015, "m_empty": 0.25, "d_body": 0.102},
}
EXPECTED_CW_STRICH = 0.345 * 1.2039 / 1.225
HERE = Path(__file__).resolve().parent
SECRET_APOGEE = 12.3456789  # Testwert; darf nie ausgegeben werden
RESULT_COLUMNS = ["apogee", "t_apogee", "t_water_end", "t_air_end",
                  "v_burnout", "h_burnout", "water_rest"]


def load_module(folder, name):
    """run.py eines anderen Ordners unter eigenem Namen laden."""
    spec = importlib.util.spec_from_file_location(name, HERE.parent / folder / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_csv(sid, config, cw_values=None, **override):
    """CSV wie der Export (Komma, CRLF), nur mit den geprüften Spalten."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    columns = ["id", "series_id", "model_version", "v_bottle", "v_water0", "p0_gauge",
               "d_nozzle", "m_empty", "c_w", "d_body", "temp0"]
    writer.writerow(columns + RESULT_COLUMNS)
    values = run.expected_cw() if cw_values is None else cw_values
    for i, cw in enumerate(values):
        row = {"id": i + 1, "series_id": sid, "model_version": "1",
               **{k: repr(v) for k, v in config.items()}, "c_w": repr(cw),
               "temp0": repr(293.15)}
        row.update(override)
        writer.writerow([row[c] for c in columns] + [SECRET_APOGEE] * len(RESULT_COLUMNS))
    return out.getvalue().encode("utf-8")


def fake_flight(fid, rid, config, **override):
    """JSON wie FlightRead, nur mit den geprüften Feldern."""
    flight = {"id": fid, "rocket_id": rid, "series_id": None, "model_version": "1",
              **config, "c_w": EXPECTED_CW_STRICH, "temp0": 293.15,
              "apogee": SECRET_APOGEE}
    flight.update(override)
    return json.dumps(flight).encode("utf-8")


class FakeApi:
    """Ersatz für run.request: merkt sich Aufrufe und Raketen."""

    def __init__(self):
        self.calls = []
        self.rockets = {}
        self.series = {}

    def __call__(self, method, path, payload=None, timeout=60):
        self.calls.append((method, path, payload))
        parts = path.strip("/").split("/")
        if method == "POST" and path == "/rockets":
            rid = 100 + len(self.rockets)
            self.rockets[rid] = {k: v for k, v in payload.items() if k != "name"}
            return 201, json.dumps({"id": rid}).encode("utf-8")
        if method == "POST" and parts[-1] == "series":
            rid = int(parts[1])
            sid = 300 + len(self.series)
            self.series[sid] = rid
            return 201, json.dumps({"id": sid}).encode("utf-8")
        if method == "GET" and parts[-1] == "flights.csv":
            sid = int(parts[1])
            config = {k: v for k, v in self.rockets[self.series[sid]].items() if k != "c_w"}
            return 200, fake_csv(sid, config)
        if method == "POST" and parts[-1] == "flights":
            rid = int(parts[1])
            config = {k: v for k, v in self.rockets[rid].items() if k != "c_w"}
            return 201, fake_flight(rid + 100, rid, config)
        raise AssertionError(f"unerwarteter Aufruf {method} {path}")


class CornerSet(unittest.TestCase):
    def test_labels_in_order(self):
        self.assertEqual([label for label, _ in run.corners()], ["E1", "E2", "E3", "E4"])

    def test_corners_equal_plan(self):
        for label, config in run.corners():
            with self.subTest(label=label):
                self.assertEqual(config, EXPECTED[label])

    def test_each_level_exactly_twice(self):
        for key in ["v_bottle", "p0_gauge", "d_nozzle", "m_empty"]:
            with self.subTest(key=key):
                values = [config[key] for _, config in run.corners()]
                self.assertEqual(len(set(values)), 2)
                self.assertTrue(all(values.count(v) == 2 for v in values))

    def test_fill_level_33_percent(self):
        for label, config in run.corners():
            with self.subTest(label=label):
                self.assertAlmostEqual(config["v_water0"] / config["v_bottle"], 0.33,
                                       places=12)

    def test_corners_are_raster_points_at_the_edges(self):
        study = load_module("parameterstudie", "parameterstudie_run")
        keys = ["v_bottle", "d_body", "p0_gauge", "d_nozzle", "m_empty"]
        raster = [{k: config[k] for k in keys} for _, config in study.rockets()]
        for key in keys:
            levels = sorted({r[key] for r in raster})
            for label, config in run.corners():
                with self.subTest(label=label, key=key):
                    self.assertIn(config[key], (levels[0], levels[-1]))
        for label, config in run.corners():
            with self.subTest(label=label):
                self.assertIn({k: config[k] for k in keys}, raster)

    def test_cw_strich_equals_tool_vergleich(self):
        tool = load_module("tool_vergleich", "tool_vergleich_run")
        self.assertEqual(run.CW_STRICH, tool.CW_STRICH)
        self.assertEqual(run.CW_STRICH, EXPECTED_CW_STRICH)

    def test_series_as_cw_plan(self):
        self.assertEqual(run.SERIES, {"mode": "forward", "param_name": "c_w",
                                      "param_start": 0.0, "param_stop": 1.0,
                                      "n_steps": 101})
        values = run.expected_cw()
        self.assertEqual(len(values), 101)
        self.assertEqual((values[0], values[-1]), (0.0, 1.0))

    def test_no_temperature_and_no_geometry_sent(self):
        wanted = set(EXPECTED["E1"]) | {"name", "c_w"}
        for label, config in run.corners():
            self.assertEqual(set(run.scan_payload(label, config)), wanted)
            self.assertEqual(set(run.flight_payload(label, config)), wanted)

    def test_flight_rocket_uses_cw_strich(self):
        for label, config in run.corners():
            self.assertEqual(run.flight_payload(label, config)["c_w"], EXPECTED_CW_STRICH)

    def test_names_are_ascii_and_distinct(self):
        names = set()
        for label, config in run.corners():
            for payload in (run.scan_payload(label, config), run.flight_payload(label, config)):
                self.assertTrue(payload["name"].isascii())
                names.add(payload["name"])
        self.assertEqual(len(names), 8)


class CheckCsv(unittest.TestCase):
    config = EXPECTED["E1"]

    def check(self, body):
        return run.check_csv(body, "E1", 5, self.config)

    def test_valid_export_passes(self):
        self.assertEqual(self.check(fake_csv(5, self.config)), 101)

    def test_missing_row_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(fake_csv(5, self.config, cw_values=run.expected_cw()[:-1]))

    def test_foreign_series_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(fake_csv(5, self.config, series_id=6))

    def test_other_model_version_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(fake_csv(5, self.config, model_version="2"))

    def test_other_temperature_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(fake_csv(5, self.config, temp0=repr(298.15)))

    def test_changed_field_fails(self):
        for key in self.config:
            with self.subTest(key=key):
                with self.assertRaises(RuntimeError):
                    self.check(fake_csv(5, self.config, **{key: repr(self.config[key] * 2)}))

    def test_other_cw_values_fail(self):
        values = run.expected_cw()
        values[50] = 0.505
        with self.assertRaises(RuntimeError):
            self.check(fake_csv(5, self.config, cw_values=values))

    def test_error_text_contains_no_values(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.check(fake_csv(5, self.config, p0_gauge=repr(6e5)))
        self.assertNotIn("600000", str(ctx.exception))
        self.assertNotIn(str(SECRET_APOGEE), str(ctx.exception))


class CheckFlight(unittest.TestCase):
    config = EXPECTED["E3"]

    def check(self, **override):
        return run.check_flight(fake_flight(7, 3, self.config, **override),
                                "E3", 3, self.config)

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

    def test_unadjusted_cw_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(c_w=0.345)

    def test_changed_water_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(v_water0=0.67e-3)

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
    def run_measure(self):
        api = FakeApi()
        out = io.StringIO()
        with mock.patch.object(run, "request", side_effect=api), redirect_stdout(out):
            results = run.measure()
        return api, results, out.getvalue()

    def test_four_corners_and_no_apogee_printed(self):
        _, results, printed = self.run_measure()
        self.assertEqual([r["label"] for r in results], ["E1", "E2", "E3", "E4"])
        self.assertEqual(results[0]["scan_file"], "scan_E1_serie_300.csv")
        self.assertEqual(results[0]["flight_file"], "modell_E1_flug_201.json")
        self.assertNotIn(str(SECRET_APOGEE), printed)

    def test_calls_per_corner(self):
        api, _, _ = self.run_measure()
        self.assertEqual(len(api.calls), 4 * 5)
        self.assertEqual(len(api.rockets), 8)
        self.assertEqual(len(api.series), 4)

    def test_rockets_sent_as_planned(self):
        api, _, _ = self.run_measure()
        configs = list(api.rockets.values())
        for i, label in enumerate(["E1", "E2", "E3", "E4"]):
            with self.subTest(label=label):
                self.assertEqual(configs[2 * i], {**EXPECTED[label], "c_w": 0.5})
                self.assertEqual(configs[2 * i + 1],
                                 {**EXPECTED[label], "c_w": EXPECTED_CW_STRICH})

    def test_series_payload_and_flight_without_body(self):
        api, _, _ = self.run_measure()
        series = [c for c in api.calls if c[1].endswith("/series")]
        flights = [c for c in api.calls if c[1].endswith("/flights")]
        self.assertEqual(len(series), 4)
        self.assertTrue(all(c[2]["param_name"] == "c_w" and c[2]["n_steps"] == 101
                            for c in series))
        self.assertEqual(len(flights), 4)
        self.assertTrue(all(c[0] == "POST" and c[2] is None for c in flights))


class Writing(unittest.TestCase):
    def results(self):
        return [{"label": "E1", "scan_rocket_id": 11, "series_id": 31,
                 "scan_file": "scan_E1_serie_31.csv", "flight_rocket_id": 12,
                 "flight_id": 21, "flight_file": "modell_E1_flug_21.json",
                 "csv": b"a,b\r\n1,2\r\n", "json": b'{"id":21}'}]

    def test_files_written_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            run.write_results(self.results(), data)
            self.assertEqual((data / "scan_E1_serie_31.csv").read_bytes(), b"a,b\r\n1,2\r\n")
            self.assertEqual((data / "modell_E1_flug_21.json").read_bytes(), b'{"id":21}')

    def test_manifest_without_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            run.write_results(self.results(), data)
            raw = (data / "modell_manifest.csv").read_bytes()
            self.assertEqual(raw, b"label,scan_rocket_id,series_id,scan_file,"
                                  b"flight_rocket_id,flight_id,flight_file\r\n"
                                  b"E1,11,31,scan_E1_serie_31.csv,12,21,"
                                  b"modell_E1_flug_21.json\r\n")

    def test_existing_tool_files_do_not_block_and_stay_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "tool_werte.csv").write_bytes(b"alt\r\n")
            with mock.patch.object(run, "wait_for_api"), \
                    mock.patch.object(run, "request", side_effect=FakeApi()), \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 0)
            self.assertEqual((data / "tool_werte.csv").read_bytes(), b"alt\r\n")
            self.assertEqual(len(list(data.glob("scan_E*_serie_*.csv"))), 4)
            self.assertEqual(len(list(data.glob("modell_E*_flug_*.json"))), 4)

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

    def test_failure_in_last_corner_writes_nothing(self):
        api = FakeApi()

        def failing(method, path, payload=None, timeout=60):
            if len(api.calls) >= 19:  # letzter Aufruf: Flug von E4
                return 422, b"{}"
            return api(method, path, payload, timeout)

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            with mock.patch.object(run, "wait_for_api"), \
                    mock.patch.object(run, "request", side_effect=failing), \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 1)
            self.assertEqual(list(data.iterdir()), [])


if __name__ == "__main__":
    unittest.main()