"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Ein Test lädt durchsatz/run.py, um Basis und Stufen zu vergleichen (keine Ausgabe).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -m unittest discover -s parameterstudie -v
"""

import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run

# Erwartete Werte, unabhängig von run.py abgeschrieben aus der Vorab-Notiz.
EXPECTED_BASE = {
    "v_bottle": 1.5e-3, "v_water0": 0.5e-3, "p0_gauge": 5e5, "d_nozzle": 0.022,
    "m_empty": 0.15, "c_w": 0.345, "d_body": 0.09,
}
EXPECTED_BOTTLES = [("F10", 1.0e-3, 0.079), ("F15", 1.5e-3, 0.09), ("F20", 2.0e-3, 0.102)]
EXPECTED_PRESSURES = [("P3", 3e5), ("P5", 5e5), ("P7", 7e5)]
EXPECTED_NOZZLES = [("D15", 0.015), ("D22", 0.022)]
EXPECTED_MASSES = [("M100", 0.10), ("M150", 0.15), ("M250", 0.25)]

MARK_DURATION = 98.7654321  # auffälliger Wert: darf nie auf der Konsole stehen
MARK_APOGEE = "4242.4242"
MARK_ERROR = "Wasserphase nicht beendet XYZ"  # Fehlertext: nur in laeufe.csv
RESULT_COLUMNS = ["apogee", "t_apogee", "t_water_end", "t_air_end",
                  "v_burnout", "h_burnout", "water_rest"]


def load_durchsatz_run():
    """durchsatz/run.py unter anderem Namen laden (beide Dateien heißen run.py)."""
    path = Path(run.__file__).resolve().parent.parent / "durchsatz" / "run.py"
    spec = importlib.util.spec_from_file_location("durchsatz_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def own_water(v_bottle, n_steps):
    """Eigene Rechnung der Wassermengen wie die API (letzter Wert exakt)."""
    start, stop = 0.05 * v_bottle, 0.95 * v_bottle
    values = [start + (stop - start) * i / (n_steps - 1) for i in range(n_steps - 1)]
    return values + [stop]


def fake_csv(series_id, config, n_steps, apogee=MARK_APOGEE, sid=None, water=None, change=None):
    """CSV wie der Export (Komma, CRLF), nur mit den geprüften Spalten."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    columns = ["id", "series_id", "v_bottle", "v_water0", "p0_gauge", "d_nozzle",
               "m_empty", "c_w", "d_body"]
    writer.writerow(columns + RESULT_COLUMNS)
    values = water if water is not None else own_water(config["v_bottle"], n_steps)
    for i, w in enumerate(values):
        cfg = {**config, **(change or {})}
        writer.writerow([i + 1, sid or series_id, repr(cfg["v_bottle"]), repr(w),
                         repr(cfg["p0_gauge"]), repr(cfg["d_nozzle"]), repr(cfg["m_empty"]),
                         repr(cfg["c_w"]), repr(cfg["d_body"])]
                        + [apogee] * len(RESULT_COLUMNS))
    return out.getvalue().encode("utf-8")


class FakeApi:
    """Ersatz für run.request: merkt sich Aufrufe, zählt wie das Original."""

    def __init__(self, series_status=None, csv_override=None):
        self.calls = []
        self.next_id = 100
        self.rockets = {}
        self.series = {}
        self.series_status = series_status or {}  # Name -> Status oder Exception
        self.csv_override = csv_override or {}  # Name -> Funktion(sid, cfg, n) -> Bytes

    def __call__(self, method, path, payload=None, timeout=60):
        run.Calls.count += 1
        self.calls.append((method, path, payload, timeout))
        self.next_id += 1
        if method == "POST" and path == "/rockets":
            self.rockets[self.next_id] = payload
            return 201, json.dumps({"id": self.next_id}).encode()
        if method == "POST" and path.endswith("/series"):
            outcome = self.series_status.get(payload["name"], 201)
            if isinstance(outcome, Exception):
                raise outcome
            if outcome == 422:
                detail = [{"loc": ["body"], "msg": MARK_ERROR, "type": "simulation_error"}]
                return 422, json.dumps({"detail": detail}).encode()
            if outcome != 201:
                return outcome, b"<html>Gateway Time-out</html>"
            rocket = self.rockets[int(path.split("/")[2])]
            self.series[self.next_id] = (payload["name"], rocket, payload["n_steps"])
            return 201, json.dumps({"id": self.next_id, "duration_s": MARK_DURATION}).encode()
        if method == "GET" and path.endswith("/flights.csv"):
            sid = int(path.split("/")[2])
            name, rocket, n_steps = self.series[sid]
            maker = self.csv_override.get(name, fake_csv)
            return 200, maker(sid, rocket, n_steps)
        raise AssertionError(f"unerwarteter Aufruf {method} {path}")


def run_measure(api):
    out = io.StringIO()
    with mock.patch.object(run, "request", api), contextlib.redirect_stdout(out):
        result = run.measure()
    return result, out.getvalue()


def name_of(label):
    return f"Parameterstudie {label}"


class Plan(unittest.TestCase):
    def test_base_as_planned_and_equal_durchsatz(self):
        self.assertEqual(run.BASE, EXPECTED_BASE)
        self.assertEqual(run.BASE, load_durchsatz_run().BASE)

    def test_levels_as_planned(self):
        self.assertEqual([(k, v["v_bottle"], v["d_body"]) for k, v in run.BOTTLES],
                         EXPECTED_BOTTLES)
        self.assertEqual([(k, v["p0_gauge"]) for k, v in run.PRESSURES], EXPECTED_PRESSURES)
        self.assertEqual([(k, v["d_nozzle"]) for k, v in run.NOZZLES], EXPECTED_NOZZLES)
        self.assertEqual([(k, v["m_empty"]) for k, v in run.MASSES], EXPECTED_MASSES)

    def test_levels_from_validation_set(self):
        """Jede Stufe ist der Wert einer Rakete aus R0 bis R9 in durchsatz/run.py."""
        ds = dict(load_durchsatz_run().rockets())
        origin = {"F10": "R8", "F15": "R0", "F20": "R9", "P3": "R1", "P5": "R0", "P7": "R2",
                  "D15": "R5", "D22": "R0", "M100": "R6", "M150": "R0", "M250": "R7"}
        for levels in (run.BOTTLES, run.PRESSURES, run.NOZZLES, run.MASSES):
            for label, values in levels:
                with self.subTest(level=label):
                    for key, value in values.items():
                        self.assertEqual(ds[origin[label]][key], value)

    def test_54_rockets_in_order(self):
        labels = [label for label, _ in run.rockets()]
        expected = [f"{b}-{p}-{d}-{m}"
                    for b, _, _ in EXPECTED_BOTTLES for p, _ in EXPECTED_PRESSURES
                    for d, _ in EXPECTED_NOZZLES for m, _ in EXPECTED_MASSES]
        self.assertEqual(labels, expected)
        self.assertEqual(len(set(labels)), 54)
        self.assertEqual(labels[0], "F10-P3-D15-M100")
        self.assertEqual(labels[1], "F10-P3-D15-M150")
        self.assertEqual(labels[-1], "F20-P7-D22-M250")

    def test_each_rocket_config(self):
        bottles = {k: (v, d) for k, v, d in EXPECTED_BOTTLES}
        pressures, nozzles, masses = (dict(EXPECTED_PRESSURES), dict(EXPECTED_NOZZLES),
                                      dict(EXPECTED_MASSES))
        for label, config in run.rockets():
            with self.subTest(label=label):
                b, p, d, m = label.split("-")
                v_bottle, d_body = bottles[b]
                self.assertEqual(config, {
                    "v_bottle": v_bottle, "d_body": d_body, "p0_gauge": pressures[p],
                    "d_nozzle": nozzles[d], "m_empty": masses[m], "c_w": 0.345,
                    "v_water0": 0.05 * v_bottle,
                })

    def test_constants(self):
        self.assertEqual((run.FILL_START, run.FILL_STOP, run.N_STEPS, run.WARMUP_STEPS),
                         (0.05, 0.95, 91, 10))
        self.assertEqual(run.WARMUP_LABEL, "F15-P5-D22-M150")
        self.assertEqual(dict(run.rockets())[run.WARMUP_LABEL],
                         {**EXPECTED_BASE, "v_water0": 0.05 * 1.5e-3})

    def test_series_payload(self):
        config = dict(run.rockets())["F20-P3-D15-M100"]
        self.assertEqual(run.series_payload("X", config, 91), {
            "name": "Parameterstudie X", "mode": "forward", "param_name": "v_water0",
            "param_start": 0.05 * 2.0e-3, "param_stop": 0.95 * 2.0e-3, "n_steps": 91,
        })

    def test_expected_water(self):
        for label, config in run.rockets():
            with self.subTest(label=label):
                values = run.expected_water(config, 91)
                v = config["v_bottle"]
                self.assertEqual(values, own_water(v, 91))
                self.assertEqual(values[-1], 0.95 * v)
                self.assertTrue(all(0 < w < v for w in values))
                for i, w in enumerate(values):
                    self.assertAlmostEqual(w / v, (5 + i) / 100, delta=1e-12)


class Measure(unittest.TestCase):
    def test_all_ok(self):
        api = FakeApi()
        (rows, exports, stop), out = run_measure(api)
        self.assertIsNone(stop)
        self.assertEqual(len(rows), 54)
        self.assertEqual([r["label"] for r in rows], [label for label, _ in run.rockets()])
        self.assertTrue(all(r["status"] == "201" and r["aufrufe"] == 3 for r in rows))
        self.assertEqual(len(api.calls), 3 * 55)  # Aufwärmlauf + 54
        self.assertEqual(sorted(exports), sorted(r["file"] for r in rows))
        self.assertTrue(all(r["file"] == f"{r['label']}_serie_{r['series_id']}.csv"
                            for r in rows))

    def test_warmup_not_counted(self):
        api = FakeApi()
        (rows, exports, _), _ = run_measure(api)
        first = api.calls[1][2]
        self.assertEqual(first["name"], "Parameterstudie F15-P5-D22-M150 Aufwaermlauf")
        self.assertEqual(first["n_steps"], 10)
        self.assertFalse(any("Aufwaermlauf" in name for name in exports))

    def test_series_requests_as_planned(self):
        api = FakeApi()
        run_measure(api)
        posts = [c for c in api.calls if c[0] == "POST" and c[1].endswith("/series")][1:]
        for (label, config), call in zip(run.rockets(), posts):
            with self.subTest(label=label):
                self.assertEqual(call[2], run.series_payload(label, config, 91))
                self.assertEqual(call[3], run.SERIES_TIMEOUT_S)

    def test_422_is_result_and_continues(self):
        api = FakeApi(series_status={name_of("F10-P3-D15-M150"): 422})
        (rows, exports, stop), out = run_measure(api)
        self.assertIsNone(stop)
        self.assertEqual(len(rows), 54)
        row = rows[1]
        self.assertEqual((row["status"], row["fehlertext"], row["aufrufe"], row["file"],
                          row["series_id"]), ("422", MARK_ERROR, 2, "", ""))
        self.assertEqual(len(exports), 53)
        self.assertNotIn(MARK_ERROR, out)

    def test_504_stops(self):
        api = FakeApi(series_status={name_of("F10-P3-D22-M100"): 504})
        (rows, exports, stop), _ = run_measure(api)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[-1]["status"], "504")
        self.assertEqual(rows[-1]["aufrufe"], 2)
        self.assertIn("F10-P3-D22-M100", stop)
        self.assertEqual(len(exports), 3)

    def test_timeout_stops(self):
        api = FakeApi(series_status={name_of("F10-P3-D15-M100"): TimeoutError()})
        (rows, _, stop), _ = run_measure(api)
        self.assertEqual((len(rows), rows[0]["status"]), (1, "timeout"))
        self.assertIsNotNone(stop)

    def test_other_error_aborts(self):
        api = FakeApi(series_status={name_of("F10-P3-D15-M100"): 500})
        with self.assertRaises(RuntimeError):
            run_measure(api)

    def test_other_oserror_raises(self):
        api = FakeApi(series_status={name_of("F10-P3-D15-M100"): ConnectionResetError()})
        with self.assertRaises(OSError):
            run_measure(api)

    def test_warmup_failure_aborts(self):
        for status in (422, 504):
            with self.subTest(status=status):
                api = FakeApi(series_status={
                    "Parameterstudie F15-P5-D22-M150 Aufwaermlauf": status})
                with self.assertRaises(RuntimeError):
                    run_measure(api)

    def test_structure_errors_abort(self):
        label = "F15-P5-D22-M150"
        config = dict(run.rockets())[label]
        bad = {
            "zeilen": lambda sid, cfg, n: fake_csv(sid, cfg, n - 1),
            "series_id": lambda sid, cfg, n: fake_csv(sid, cfg, n, sid=sid + 1),
            "wasser": lambda sid, cfg, n: fake_csv(
                sid, cfg, n, water=[w * (1 + 1e-15) if i == 7 else w
                                    for i, w in enumerate(own_water(cfg["v_bottle"], n))]),
            "druck": lambda sid, cfg, n: fake_csv(sid, cfg, n, change={"p0_gauge": 5e5 + 1}),
            "c_w": lambda sid, cfg, n: fake_csv(sid, cfg, n, change={"c_w": 0.5}),
            "d_body": lambda sid, cfg, n: fake_csv(sid, cfg, n, change={"d_body": 0.1}),
        }
        self.assertEqual(config["v_bottle"], 1.5e-3)
        for what, maker in bad.items():
            with self.subTest(what=what):
                api = FakeApi(csv_override={name_of(label): maker})
                with self.assertRaises(RuntimeError):
                    run_measure(api)

    def test_empty_or_nan_results_do_not_abort(self):
        """Endlichkeit bewertet erst die Auswertung (Vorab-Notiz Abschnitt 2)."""
        for apogee in ("", "nan", "inf"):
            with self.subTest(apogee=apogee):
                maker = lambda sid, cfg, n, a=apogee: fake_csv(sid, cfg, n, apogee=a)
                api = FakeApi(csv_override={name_of("F10-P3-D15-M100"): maker})
                (rows, exports, stop), _ = run_measure(api)
                self.assertIsNone(stop)
                self.assertEqual(len(exports), 54)

    def test_no_values_on_console(self):
        api = FakeApi(series_status={name_of("F10-P3-D15-M150"): 422})
        (rows, _, _), out = run_measure(api)
        for mark in (str(MARK_DURATION), MARK_APOGEE, MARK_ERROR):
            self.assertNotIn(mark, out)
        for row in rows:
            self.assertNotIn(row["t_client_s"], out)
            self.assertNotIn(row["t_lauf_s"], out)


class Main(unittest.TestCase):
    def run_main(self, api, data_dir):
        out = io.StringIO()
        with mock.patch.object(run, "request", api), \
                mock.patch.object(run, "wait_for_api", lambda: None), \
                contextlib.redirect_stdout(out):
            code = run.main(data_dir)
        return code, out.getvalue()

    def test_writes_exports_unchanged_and_runs(self):
        api = FakeApi(series_status={name_of("F10-P3-D15-M150"): 422})
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            code, out = self.run_main(api, data)
            self.assertEqual(code, 0)
            raw = (data / run.RUNS_NAME).read_bytes()
            self.assertTrue(raw.endswith(b"\r\n"))
            self.assertEqual(raw.count(b"\r\n"), 55)
            with open(data / run.RUNS_NAME, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(list(rows[0]), run.RUNS_COLUMNS)
            self.assertEqual(len(rows), 54)
            files = sorted(p.name for p in data.iterdir() if p.name != run.RUNS_NAME)
            self.assertEqual(files, sorted(r["file"] for r in rows if r["file"]))
            self.assertEqual(len(files), 53)
            for r in rows:
                if r["file"]:
                    name, rocket, n = api.series[int(r["series_id"])]
                    self.assertEqual((data / r["file"]).read_bytes(),
                                     fake_csv(int(r["series_id"]), rocket, n))
            self.assertIn("davon mit 422: 1", out)

    def test_refuses_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / run.RUNS_NAME).write_text("x")
            api = FakeApi()
            code, _ = self.run_main(api, data)
            self.assertEqual(code, 2)
            self.assertEqual(api.calls, [])
            self.assertEqual((data / run.RUNS_NAME).read_text(), "x")

    def test_abort_writes_nothing(self):
        api = FakeApi(series_status={name_of("F20-P7-D22-M250"): 500})
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            code, _ = self.run_main(api, data)
            self.assertEqual(code, 1)
            self.assertFalse(data.exists())

    def test_stop_writes_rows_so_far(self):
        api = FakeApi(series_status={name_of("F10-P3-D22-M100"): 504})
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            code, _ = self.run_main(api, data)
            self.assertEqual(code, 3)
            with open(data / run.RUNS_NAME, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["status"] for r in rows], ["201", "201", "201", "504"])
            self.assertEqual(len(list(data.iterdir())), 4)


if __name__ == "__main__":
    unittest.main()