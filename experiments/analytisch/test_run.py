"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Ein Test lädt durchsatz/run.py, um die Raketen zu vergleichen (keine Ausgabe).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -W error -m unittest discover -s analytisch -v
"""

import csv
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import run

# Erwartete Raketen, unabhängig von run.py abgeschrieben aus dem Validierungssatz.
EXPECTED_BASE = {
    "v_bottle": 1.5e-3, "v_water0": 0.5e-3, "p0_gauge": 5e5, "d_nozzle": 0.022,
    "m_empty": 0.15, "c_w": 0.345, "d_body": 0.09,
}
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
LABELS = [f"R{i}" for i in range(10)]

# Auffällige Werte: dürfen nie auf der Konsole stehen.
MARK = {"apogee": 4242.4242, "h_burnout": 31.4159, "v_burnout": 27.1828,
        "water_rest": 1.2345e-5}
MARK_ERROR = "Wasserphase nicht beendet 98765"


def load_durchsatz_run():
    """durchsatz/run.py unter anderem Namen laden (beide Dateien heißen run.py)."""
    path = Path(run.__file__).resolve().parent.parent / "durchsatz" / "run.py"
    spec = importlib.util.spec_from_file_location("durchsatz_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_flight(fid, rid, config, **override):
    """JSON wie FlightRead, nur mit den geprüften Feldern."""
    flight = {"id": fid, "rocket_id": rid, "series_id": None, "model_version": "1",
              **config, "temp0": 293.15, **MARK}
    flight.update(override)
    return json.dumps(flight).encode("utf-8")


def error_body(msg=MARK_ERROR):
    return json.dumps({"detail": [{"loc": ["body"], "msg": msg, "type": "value_error"}]}
                      ).encode("utf-8")


class FakeApi:
    """Ersatz für run.request: Rakete i bekommt ID 100+i, Flug ID 300+i."""

    def __init__(self, flight_status=None, rocket_status=None):
        self.calls = []
        self.configs = {}
        self.flight_status = flight_status or {}  # Name -> Status
        self.rocket_status = rocket_status or {}
        self.names = {}  # Raketen-ID -> Name

    def __call__(self, method, path, payload=None, timeout=60):
        self.calls.append((method, path, payload))
        if method == "POST" and path == "/rockets":
            name = payload["name"]
            if name in self.rocket_status:
                return self.rocket_status[name], error_body()
            rid = 100 + len(self.configs)
            self.configs[rid] = {k: v for k, v in payload.items() if k != "name"}
            self.names[rid] = name
            return 201, json.dumps({"id": rid}).encode("utf-8")
        rid = int(path.split("/")[2])
        status = self.flight_status.get(self.names[rid], 201)
        if status != 201:
            return status, error_body()
        return 201, fake_flight(rid + 200, rid, self.configs[rid])


def run_measure(api):
    out = io.StringIO()
    with mock.patch.object(run, "request", side_effect=api), redirect_stdout(out):
        rows, files = run.measure()
    return rows, files, out.getvalue()


class Plan(unittest.TestCase):
    def test_base(self):
        self.assertEqual(run.BASE, EXPECTED_BASE)

    def test_rockets_as_planned(self):
        self.assertEqual([label for label, _ in run.rockets()], LABELS)
        for label, config in run.rockets():
            with self.subTest(label=label):
                self.assertEqual(config, {**EXPECTED_BASE, **EXPECTED[label]})

    def test_rockets_equal_durchsatz(self):
        self.assertEqual(run.rockets(), load_durchsatz_run().rockets())

    def test_cases(self):
        self.assertEqual(run.CASES, {"F1": 0.0, "F2": 0.345})

    def test_runs_order_and_count(self):
        order = [(label, case) for label, case, _ in run.runs()]
        self.assertEqual(order, [(label, case) for label in LABELS for case in ("F1", "F2")])

    def test_runs_differ_only_in_cw(self):
        rockets = dict(run.rockets())
        for label, case, config in run.runs():
            with self.subTest(label=label, case=case):
                self.assertEqual(config, {**rockets[label], "c_w": run.CASES[case]})

    def test_f2_is_nominal_configuration(self):
        for label, case, config in run.runs():
            if case == "F2":
                self.assertEqual(config, {**EXPECTED_BASE, **EXPECTED[label]})

    def test_no_temperature_and_no_geometry_sent(self):
        for label, case, config in run.runs():
            payload = run.rocket_payload(label, case, config)
            self.assertEqual(set(payload), set(EXPECTED_BASE) | {"name"})

    def test_names_are_ascii(self):
        for label, case, config in run.runs():
            self.assertTrue(run.rocket_payload(label, case, config)["name"].isascii())


class CheckFlight(unittest.TestCase):
    config = {**EXPECTED_BASE, "c_w": 0.0}

    def check(self, **override):
        return run.check_flight(fake_flight(7, 3, self.config, **override),
                                "R0 F1", 3, self.config)

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

    def test_missing_or_invalid_result_fields_fail(self):
        for key in run.RESULT_FIELDS:
            for bad in (None, "1.0", True):
                with self.subTest(key=key, bad=bad), self.assertRaises(RuntimeError):
                    self.check(**{key: bad})

    def test_missing_id_fails(self):
        with self.assertRaises(RuntimeError):
            self.check(id=None)

    def test_error_text_contains_no_values(self):
        for override in ({"c_w": 0.345}, {"apogee": None}):
            with self.assertRaises(RuntimeError) as ctx:
                self.check(**override)
            text = str(ctx.exception)
            for value in (0.345, *MARK.values()):
                self.assertNotIn(str(value), text)


class Measure(unittest.TestCase):
    def test_twenty_runs_in_order(self):
        rows, files, _ = run_measure(FakeApi())
        self.assertEqual([(r["label"], r["fall"]) for r in rows],
                         [(label, case) for label in LABELS for case in ("F1", "F2")])
        self.assertEqual(len(files), 20)
        self.assertEqual(rows[0]["file"], "R0_F1_flug_300.json")
        self.assertEqual(rows[1]["file"], "R0_F2_flug_301.json")

    def test_new_rocket_per_run_and_flight_without_body(self):
        api = FakeApi()
        run_measure(api)
        self.assertEqual(len(api.calls), 40)
        rocket_posts = [c for c in api.calls if c[1] == "/rockets"]
        flight_posts = [c for c in api.calls if c[1].endswith("/flights")]
        self.assertEqual(len(rocket_posts), 20)
        self.assertEqual([p for _, _, p in flight_posts], [None] * 20)

    def test_cw_sent_as_planned(self):
        api = FakeApi()
        run_measure(api)
        sent = [p["c_w"] for _, path, p in api.calls if path == "/rockets"]
        self.assertEqual(sent, [0.0, 0.345] * 10)

    def test_cw_column_as_text(self):
        rows, _, _ = run_measure(FakeApi())
        self.assertEqual([r["c_w"] for r in rows[:2]], ["0.0", "0.345"])

    def test_422_recorded_and_continues(self):
        rows, files, out = run_measure(FakeApi(flight_status={"Analytisch R3 F2": 422}))
        self.assertEqual(len(rows), 20)
        row = rows[7]
        self.assertEqual((row["label"], row["fall"], row["status"]), ("R3", "F2", "422"))
        self.assertEqual((row["flight_id"], row["file"]), ("", ""))
        self.assertEqual(row["fehler"], MARK_ERROR)
        self.assertEqual(len(files), 19)
        self.assertNotIn(MARK_ERROR, out)

    def test_other_flight_status_aborts(self):
        with self.assertRaises(RuntimeError):
            run_measure(FakeApi(flight_status={"Analytisch R0 F1": 500}))

    def test_rocket_422_aborts(self):
        with self.assertRaises(RuntimeError):
            run_measure(FakeApi(rocket_status={"Analytisch R5 F1": 422}))

    def test_no_values_printed(self):
        _, _, out = run_measure(FakeApi())
        for value in MARK.values():
            self.assertNotIn(str(value), out)
        self.assertNotIn("0.345", out)


class Writing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, api):
        out = io.StringIO()
        with mock.patch.object(run, "request", side_effect=api), \
                mock.patch.object(run, "wait_for_api"), redirect_stdout(out):
            code = run.main(self.data)
        return code, out.getvalue()

    def read_manifest(self):
        with open(self.data / run.MANIFEST_NAME, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_json_written_byte_for_byte(self):
        code, _ = self.run_main(FakeApi())
        self.assertEqual(code, 0)
        body = (self.data / "R0_F1_flug_300.json").read_bytes()
        self.assertEqual(body, fake_flight(300, 100, {**EXPECTED_BASE, "c_w": 0.0}))

    def test_manifest_columns_and_rows(self):
        self.run_main(FakeApi())
        rows = self.read_manifest()
        self.assertEqual(list(rows[0]), run.MANIFEST_COLUMNS)
        self.assertEqual(len(rows), 20)
        self.assertEqual(sorted(p.name for p in self.data.glob("*.json")),
                         sorted(r["file"] for r in rows))

    def test_422_written_with_error_text(self):
        code, out = self.run_main(FakeApi(flight_status={"Analytisch R0 F1": 422}))
        self.assertEqual(code, 0)
        row = self.read_manifest()[0]
        self.assertEqual((row["status"], row["fehler"], row["file"]),
                         ("422", MARK_ERROR, ""))
        self.assertIn("davon mit 422: 1", out)

    def test_existing_manifest_aborts_without_api(self):
        self.data.mkdir()
        (self.data / run.MANIFEST_NAME).write_text("x", encoding="utf-8")
        api = FakeApi()
        code, _ = self.run_main(api)
        self.assertEqual(code, 2)
        self.assertEqual(api.calls, [])

    def test_failure_writes_nothing(self):
        code, _ = self.run_main(FakeApi(flight_status={"Analytisch R9 F2": 500}))
        self.assertEqual(code, 1)
        self.assertFalse(self.data.exists())


class RealHttp(unittest.TestCase):
    """request() und error_text() gegen einen kleinen echten HTTP-Server."""

    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                received = self.rfile.read(length)
                if self.path == "/api/rockets/1/flights":
                    status, body = 201, b'{"id": 5}'
                elif self.path == "/api/rockets/2/flights":
                    status, body = 422, error_body()
                elif self.path == "/api/rockets/3/flights":
                    status, body = 422, b"kein json"
                else:
                    status, body = 201, received
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/api"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, method, path, payload=None):
        with mock.patch.object(run, "API_BASE", self.base):
            return run.request(method, path, payload)

    def test_201_returns_body(self):
        self.assertEqual(self.call("POST", "/rockets/1/flights"), (201, b'{"id": 5}'))

    def test_payload_sent_as_json(self):
        status, body = self.call("POST", "/rockets", {"name": "x", "c_w": 0.0})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body), {"name": "x", "c_w": 0.0})

    def test_422_body_and_error_text(self):
        status, body = self.call("POST", "/rockets/2/flights")
        self.assertEqual(status, 422)
        self.assertEqual(run.error_text(body), MARK_ERROR)

    def test_error_text_without_json(self):
        status, body = self.call("POST", "/rockets/3/flights")
        self.assertEqual((status, run.error_text(body)), (422, "kein json"))


if __name__ == "__main__":
    unittest.main()