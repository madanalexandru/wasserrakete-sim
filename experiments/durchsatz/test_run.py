"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -m unittest discover -s durchsatz -v
"""

import contextlib
import csv
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import run

# Erwartete Raketen, unabhängig von run.py abgeschrieben aus der Vorab-Notiz.
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
MARK_DURATION = 98.7654321  # auffälliger Wert: darf nie auf der Konsole stehen
MARK_APOGEE = "4242.4242"


def fake_csv(series_id, n_steps, apogee=MARK_APOGEE, p0=None, sid=None):
    """CSV wie der Export (Komma, CRLF), nur mit den geprüften Spalten."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["id", "series_id", "p0_gauge"] + run.RESULT_COLUMNS)
    values = p0 if p0 is not None else run.expected_p0(n_steps)
    for i, p in enumerate(values):
        writer.writerow([i + 1, sid or series_id, repr(p)] + [apogee] * len(run.RESULT_COLUMNS))
    return out.getvalue().encode("utf-8")


class FakeApi:
    """Ersatz für run.request: merkt sich Aufrufe, zählt wie das Original."""

    def __init__(self, series_status=None, apogee_by_pass=None):
        self.calls = []
        self.next_id = 100
        self.n_steps = {}
        self.series_status = series_status or {}  # (Name) -> Status oder Exception
        self.apogee_by_pass = apogee_by_pass or {}
        self.series_names = {}

    def __call__(self, method, path, payload=None, timeout=60):
        run.Calls.count += 1
        self.calls.append((method, path, payload, timeout))
        self.next_id += 1
        if method == "POST" and path == "/rockets":
            return 201, json.dumps({"id": self.next_id}).encode()
        if method == "POST" and path.endswith("/series"):
            outcome = self.series_status.get(payload["name"], 201)
            if isinstance(outcome, Exception):
                raise outcome
            if outcome != 201:
                return outcome, b"<html>Gateway Time-out</html>"
            self.n_steps[self.next_id] = payload["n_steps"]
            self.series_names[self.next_id] = payload["name"]
            return 201, json.dumps({"id": self.next_id, "duration_s": MARK_DURATION}).encode()
        if method == "GET" and path.endswith("/flights.csv"):
            sid = int(path.split("/")[2])
            name = self.series_names[sid]
            apogee = self.apogee_by_pass.get(name, MARK_APOGEE)
            return 200, fake_csv(sid, self.n_steps[sid], apogee=apogee)
        raise AssertionError(f"unerwarteter Aufruf {method} {path}")


def run_measure(api):
    out = io.StringIO()
    with mock.patch.object(run, "request", api), contextlib.redirect_stdout(out):
        result = run.measure()
    return result, out.getvalue()


class Plan(unittest.TestCase):
    def test_labels_in_order(self):
        self.assertEqual([label for label, _ in run.rockets()], [f"R{i}" for i in range(10)])

    def test_each_rocket_as_planned(self):
        self.assertEqual(run.BASE, EXPECTED_BASE)
        for label, config in run.rockets():
            with self.subTest(label=label):
                self.assertEqual(config, {**EXPECTED_BASE, **EXPECTED[label]})

    def test_series_as_planned(self):
        self.assertEqual(run.SERIES, {
            "mode": "forward", "param_name": "p0_gauge",
            "param_start": 1e3, "param_stop": 1e6, "n_steps": 1000,
        })
        self.assertEqual((run.WARMUP_STEPS, run.PASSES), (10, 3))

    def test_client_waits_longer_than_nginx(self):
        self.assertGreater(run.SERIES_TIMEOUT_S, 300)

    def test_expected_p0(self):
        values = run.expected_p0(1000)
        self.assertEqual(len(values), 1000)
        self.assertEqual((values[0], values[-1]), (1e3, 1e6))
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))

    def test_expected_p0_like_api(self):
        # Formel abgeschrieben aus SeriesCreate.param_values (backend/app/schemas.py).
        span, last = 1e6 - 1e3, 999
        api = [1e3 + span * i / last for i in range(last)] + [1e6]
        self.assertEqual(run.expected_p0(1000), api)

    def test_names_are_ascii(self):
        for label, config in run.rockets():
            self.assertTrue(run.rocket_payload(label, config, 1)["name"].isascii())
            self.assertTrue(run.series_payload(label, 1, 1000)["name"].isascii())


class CheckCsv(unittest.TestCase):
    def rows(self, **kw):
        return run.parse_csv(fake_csv(7, 5, **kw))

    def test_valid_passes(self):
        run.check_csv(self.rows(), 7, 5)

    def test_wrong_row_count_fails(self):
        with self.assertRaises(RuntimeError):
            run.check_csv(self.rows(), 7, 6)

    def test_foreign_series_fails(self):
        with self.assertRaises(RuntimeError):
            run.check_csv(self.rows(sid=8), 7, 5)

    def test_other_pressures_fail(self):
        p0 = run.expected_p0(5)
        p0[2] += 1.0
        with self.assertRaises(RuntimeError):
            run.check_csv(self.rows(p0=p0), 7, 5)

    def test_empty_result_fails(self):
        with self.assertRaises(RuntimeError):
            run.check_csv(self.rows(apogee=""), 7, 5)

    def test_error_text_contains_no_values(self):
        with self.assertRaises(RuntimeError) as ctx:
            run.check_csv(self.rows(sid=8), 7, 6)
        self.assertNotIn(MARK_APOGEE, str(ctx.exception))


class Measure(unittest.TestCase):
    def test_warmup_then_three_passes(self):
        api = FakeApi()
        (times, first_csv, reason), _ = run_measure(api)
        series_posts = [c for c in api.calls if c[1].endswith("/series")]
        self.assertEqual(len(series_posts), 1 + 30)
        self.assertEqual(series_posts[0][2]["n_steps"], 10)
        self.assertTrue(all(c[2]["n_steps"] == 1000 for c in series_posts[1:]))
        self.assertTrue(all(c[3] == run.SERIES_TIMEOUT_S for c in series_posts))
        self.assertIsNone(reason)
        self.assertEqual(len(times), 30)
        self.assertEqual(len(first_csv), 10)

    def test_order_and_new_rocket_per_series(self):
        api = FakeApi()
        (times, _, _), _ = run_measure(api)
        self.assertEqual([(t["durchgang"], t["label"]) for t in times],
                         [(p, f"R{i}") for p in (1, 2, 3) for i in range(10)])
        self.assertEqual(len({t["rocket_id"] for t in times}), 30)

    def test_three_calls_per_series(self):
        (times, _, _), _ = run_measure(FakeApi())
        self.assertTrue(all(t["aufrufe"] == 3 for t in times))

    def test_times_recorded(self):
        (times, _, _), _ = run_measure(FakeApi())
        for t in times:
            self.assertEqual(t["status"], "201")
            self.assertEqual(float(t["duration_s"]), MARK_DURATION)
            self.assertGreaterEqual(float(t["t_client_s"]), 0.0)

    def test_files_only_for_first_pass(self):
        (times, first_csv, _), _ = run_measure(FakeApi())
        files = [t["file"] for t in times]
        self.assertTrue(all(f for f in files[:10]))
        self.assertTrue(all(f == "" for f in files[10:]))
        self.assertEqual(sorted(first_csv), sorted(files[:10]))

    def test_no_values_printed(self):
        _, output = run_measure(FakeApi())
        self.assertNotIn(MARK_APOGEE, output)
        self.assertNotIn(str(MARK_DURATION)[:6], output)

    def test_different_results_abort(self):
        api = FakeApi(apogee_by_pass={"Durchsatz R4 D3": "1.0"})
        with self.assertRaises(RuntimeError) as ctx:
            run_measure(api)
        self.assertIn("R4 D3", str(ctx.exception))
        self.assertNotIn("1.0", str(ctx.exception).replace("R4 D3", ""))

    def test_504_is_recorded_and_stops(self):
        api = FakeApi(series_status={"Durchsatz R2 D1": 504})
        (times, first_csv, reason), _ = run_measure(api)
        self.assertEqual(len(times), 3)
        self.assertEqual(times[-1]["status"], "504")
        self.assertEqual(times[-1]["aufrufe"], 2)
        self.assertIn("R2 D1", reason)
        self.assertEqual(len(first_csv), 2)

    def test_client_timeout_is_recorded(self):
        api = FakeApi(series_status={"Durchsatz R0 D2": TimeoutError("timed out")})
        (times, _, reason), _ = run_measure(api)
        self.assertEqual(times[-1]["status"], "timeout")
        self.assertIn("R0 D2", reason)

    def test_other_errors_abort(self):
        for outcome in (422, 500, ConnectionRefusedError()):
            with self.subTest(outcome=outcome):
                api = FakeApi(series_status={"Durchsatz R1 D1": outcome})
                with self.assertRaises((RuntimeError, ConnectionRefusedError)):
                    run_measure(api)


class Writing(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def main(self, api):
        out = io.StringIO()
        with mock.patch.object(run, "request", api), \
                mock.patch.object(run, "wait_for_api", lambda: None), \
                contextlib.redirect_stdout(out):
            return run.main(self.dir)

    def test_csv_written_byte_for_byte(self):
        self.assertEqual(self.main(FakeApi()), 0)
        name = sorted(p.name for p in self.dir.glob("R0_*.csv"))[0]
        sid = int(name.split("_")[-1].removesuffix(".csv"))
        self.assertEqual((self.dir / name).read_bytes(), fake_csv(sid, 1000))
        self.assertIn(b"\r\n", (self.dir / name).read_bytes())

    def test_times_file_columns_and_rows(self):
        self.main(FakeApi())
        with open(self.dir / run.TIMES_NAME, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), run.TIMES_COLUMNS)
        self.assertEqual(len(rows), 30)

    def test_existing_times_abort_without_api(self):
        (self.dir / run.TIMES_NAME).write_text("x")
        api = FakeApi()
        self.assertEqual(self.main(api), 2)
        self.assertEqual(api.calls, [])
        self.assertEqual((self.dir / run.TIMES_NAME).read_text(), "x")

    def test_failure_writes_nothing(self):
        api = FakeApi(series_status={"Durchsatz R5 D1": 500})
        self.assertEqual(self.main(api), 1)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_504_writes_partial_times_and_returns_3(self):
        api = FakeApi(series_status={"Durchsatz R9 D3": 504})
        self.assertEqual(self.main(api), 3)
        with open(self.dir / run.TIMES_NAME, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[-1]["status"], "504")


class RealHttp(unittest.TestCase):
    """request() und post_series() gegen einen kleinen echten HTTP-Server."""

    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                if "slow" in self.path:
                    time.sleep(1.5)
                try:
                    self.send_response(504 if "gateway" in self.path else 201)
                    self.end_headers()
                    self.wfile.write(b"{}")
                except BrokenPipeError:
                    pass  # Client hat nach seiner Wartezeit aufgelegt (gewollt)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_request_counts_calls(self):
        with mock.patch.object(run, "API_BASE", self.base):
            before = run.Calls.count
            run.request("GET", "/health")
            run.request("POST", "/rockets", {"a": 1})
            self.assertEqual(run.Calls.count - before, 2)

    def test_wait_for_api_resets_counter(self):
        with mock.patch.object(run, "API_BASE", self.base):
            run.Calls.count = 5
            run.wait_for_api(seconds=5)
            self.assertEqual(run.Calls.count, 0)

    def test_504_status_as_text(self):
        with mock.patch.object(run, "API_BASE", self.base):
            status, _, seconds = run.post_series("gateway", {"n": 1})
        self.assertEqual(status, "504")
        self.assertGreaterEqual(seconds, 0.0)

    def test_client_timeout_detected(self):
        with mock.patch.object(run, "API_BASE", self.base), \
                mock.patch.object(run, "SERIES_TIMEOUT_S", 0.5):
            status, body, seconds = run.post_series("slow", {"n": 1})
        self.assertEqual((status, body), ("timeout", b""))
        self.assertGreaterEqual(seconds, 0.5)

    def test_time_measured_around_post(self):
        with mock.patch.object(run, "API_BASE", self.base):
            status, _, seconds = run.post_series("slow", {"n": 1})
        self.assertEqual(status, "201")
        self.assertGreaterEqual(seconds, 1.5)


if __name__ == "__main__":
    unittest.main()