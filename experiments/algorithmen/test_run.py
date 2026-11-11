"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Ein Test liest die echten Eingaben aus durchsatz/ (Struktur, keine Ausgabe).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -W error -m unittest discover -s algorithmen -v
"""

import contextlib
import csv
import importlib.util
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

LABELS = [f"R{i}" for i in range(10)]
MARK_DURATION = 98.7654321  # auffällige Werte: dürfen nie auf der Konsole stehen
MARK_APOGEE = "4242.4242"
MARK_EVALS = "777"
MARK_H = 1234.5678
MARK_ERROR = "Restintervall 31415.9 Pa"


def load_durchsatz_run():
    """durchsatz/run.py unter anderem Namen laden (beide Dateien heißen run.py)."""
    path = Path(run.__file__).resolve().parent.parent / "durchsatz" / "run.py"
    spec = importlib.util.spec_from_file_location("durchsatz_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_csv(series_id, searcher, targets, sid=None, evals=MARK_EVALS):
    """Inverser Export wie die API (Komma, CRLF), nur mit den geprüften Spalten."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["id", "series_id", "p0_gauge", "target_apogee", "searcher",
                     "search_evaluations", "apogee"])
    for i, t in enumerate(targets):
        writer.writerow([i + 1, sid or series_id, "500000.0", repr(t), searcher, evals,
                         MARK_APOGEE])
    return out.getvalue().encode("utf-8")


class FakeApi:
    """Ersatz für run.request: merkt sich Aufrufe, zählt wie das Original."""

    def __init__(self, series_status=None):
        self.calls = []
        self.next_id = 100
        self.series = {}
        self.series_status = series_status or {}  # Name -> Status oder Exception

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
            if outcome == 422:
                detail = [{"loc": ["body"], "msg": f"Schritt 3: {MARK_ERROR}",
                           "type": "simulation_error"}]
                return 422, json.dumps({"detail": detail}).encode()
            if outcome != 201:
                return outcome, b"<html>Gateway Time-out</html>"
            self.series[self.next_id] = payload
            return 201, json.dumps({"id": self.next_id, "duration_s": MARK_DURATION}).encode()
        if method == "GET" and path.endswith("/flights.csv"):
            sid = int(path.split("/")[2])
            p = self.series[sid]
            targets = run.expected_targets(p["param_start"], p["param_stop"], p["n_steps"])
            return 200, fake_csv(sid, p["searcher"], targets)
        raise AssertionError(f"unerwarteter Aufruf {method} {path}")


def h_all(exclude=()):
    return {label: MARK_H + i for i, label in enumerate(LABELS) if label not in exclude}


def run_measure(api, h_pmax=None):
    out = io.StringIO()
    with mock.patch.object(run, "request", api), contextlib.redirect_stdout(out):
        result = run.measure(h_pmax or h_all())
    return result, out.getvalue()


def write_inputs(durchsatz_dir, included=None, last_p0=1e6, rows=1000, h=MARK_H):
    """Erfundene monotonie.csv und Vorwärts-Exporte wie in durchsatz/."""
    (durchsatz_dir / "results").mkdir(parents=True)
    (durchsatz_dir / "data").mkdir()
    included = included or {label: "ja" for label in LABELS}
    with open(durchsatz_dir / "results" / "monotonie.csv", "w", newline="",
              encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["label", "file", "m1", "m2", "abnahmen", "abnahmen_le0",
                         "im_vergleich"])
        for i, label in enumerate(LABELS):
            file = f"{label}_serie_{16 + i}.csv"
            writer.writerow([label, file, "nein", "ja", 6, 6, included[label]])
            with open(durchsatz_dir / "data" / file, "w", newline="", encoding="utf-8") as g:
                w = csv.writer(g, lineterminator="\r\n")
                w.writerow(["id", "p0_gauge", "apogee"])
                for k in range(rows - 1):
                    w.writerow([k + 1, repr(1e3 + k), "0.5"])
                w.writerow([rows, repr(last_p0), repr(h + i)])


class Plan(unittest.TestCase):
    def test_rockets_equal_durchsatz(self):
        other = load_durchsatz_run()
        self.assertEqual(run.BASE, other.BASE)
        self.assertEqual(run.CHANGES, other.CHANGES)
        self.assertEqual(run.rockets(), other.rockets())

    def test_searchers_and_targets_as_planned(self):
        self.assertEqual(run.SEARCHERS, ["binary", "exponential", "interpolation"])
        self.assertEqual((run.N_TARGETS, run.TARGET_LOW, run.TARGET_HIGH), (40, 0.05, 0.95))
        self.assertEqual((run.WARMUP_TARGETS, run.P_MAX, run.FORWARD_STEPS), (2, 1e6, 1000))

    def test_client_waits_longer_than_nginx(self):
        self.assertGreater(run.SERIES_TIMEOUT_S, 300)

    def test_expected_targets_like_api(self):
        # Formel abgeschrieben aus SeriesCreate.param_values (backend/app/schemas.py).
        start, stop = 0.05 * 87.3, 0.95 * 87.3
        last = 39
        api = [start + (stop - start) * i / last for i in range(last)] + [stop]
        values = run.expected_targets(start, stop, 40)
        self.assertEqual(values, api)
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))

    def test_last_target_exactly_stop(self):
        # Für dieses h verfehlt start + (stop - start) den Wert stop um eine Rundung.
        h = 57.223752120642565
        start, stop = 0.05 * h, 0.95 * h
        self.assertNotEqual(start + (stop - start), stop)
        self.assertEqual(run.expected_targets(start, stop, 40)[-1], stop)

    def test_series_payload(self):
        p = run.series_payload("R3", "exponential", 1.0, 19.0, 40)
        self.assertEqual(p, {
            "name": "Algorithmen R3 exponential", "mode": "inverse",
            "param_name": "target_apogee", "param_start": 1.0, "param_stop": 19.0,
            "n_steps": 40, "searcher": "exponential",
        })

    def test_names_are_ascii(self):
        for label, config in run.rockets():
            for s in run.SEARCHERS:
                self.assertTrue(run.rocket_payload(label, config, s)["name"].isascii())


class Inputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "durchsatz"

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid(self):
        write_inputs(self.dir)
        self.assertEqual(run.load_inputs(self.dir), h_all())

    def test_excluded_rocket_skipped(self):
        write_inputs(self.dir, included={**{l: "ja" for l in LABELS}, "R4": "nein"})
        self.assertEqual(list(run.load_inputs(self.dir)), [l for l in LABELS if l != "R4"])

    def test_invalid_flag(self):
        write_inputs(self.dir, included={**{l: "ja" for l in LABELS}, "R1": "vielleicht"})
        with self.assertRaisesRegex(ValueError, "ungültig"):
            run.load_inputs(self.dir)

    def test_missing_rocket(self):
        write_inputs(self.dir)
        path = self.dir / "results" / "monotonie.csv"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Reihenfolge"):
            run.load_inputs(self.dir)

    def test_last_row_not_p_max(self):
        write_inputs(self.dir, last_p0=999000.0)
        with self.assertRaisesRegex(ValueError, "P_MAX"):
            run.load_inputs(self.dir)

    def test_wrong_row_count(self):
        write_inputs(self.dir, rows=999)
        with self.assertRaisesRegex(ValueError, "Zeilenzahl"):
            run.load_inputs(self.dir)

    def test_apogee_not_positive(self):
        write_inputs(self.dir, h=-20.0)
        with self.assertRaisesRegex(ValueError, "nicht positiv") as ctx:
            run.load_inputs(self.dir)
        self.assertNotIn("-20", str(ctx.exception))

    def test_real_inputs_load(self):
        # Echte Dateien: nur Struktur, keine Ausgabe der Höhen.
        h = run.load_inputs(run.DURCHSATZ_DIR)
        self.assertEqual(list(h), LABELS)
        self.assertTrue(all(v > 0 for v in h.values()))


class CheckCsv(unittest.TestCase):
    targets = run.expected_targets(2.0, 38.0, 5)

    def rows(self, **kw):
        return run.parse_csv(fake_csv(7, kw.pop("searcher", "binary"),
                                      kw.pop("targets", self.targets), **kw))

    def test_valid_passes(self):
        run.check_csv(self.rows(), 7, "binary", self.targets)

    def test_wrong_row_count_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Zeilen"):
            run.check_csv(self.rows(targets=self.targets[:4]), 7, "binary", self.targets)

    def test_foreign_series_fails(self):
        with self.assertRaisesRegex(RuntimeError, "fremder"):
            run.check_csv(self.rows(sid=8), 7, "binary", self.targets)

    def test_other_searcher_fails(self):
        with self.assertRaisesRegex(RuntimeError, "Suchverfahren"):
            run.check_csv(self.rows(searcher="exponential"), 7, "binary", self.targets)

    def test_other_targets_fail(self):
        moved = self.targets[:2] + [self.targets[2] + 1e-9] + self.targets[3:]
        with self.assertRaisesRegex(RuntimeError, "Zielhöhen"):
            run.check_csv(self.rows(targets=moved), 7, "binary", self.targets)

    def test_empty_evaluations_fail(self):
        with self.assertRaisesRegex(RuntimeError, "leere"):
            run.check_csv(self.rows(evals=""), 7, "binary", self.targets)

    def test_error_text_contains_no_values(self):
        with self.assertRaises(RuntimeError) as ctx:
            run.check_csv(self.rows(sid=8), 7, "binary", self.targets)
        self.assertNotIn(MARK_APOGEE, str(ctx.exception))


class Measure(unittest.TestCase):
    def series_posts(self, api):
        return [c for c in api.calls if c[1].endswith("/series")]

    def test_warmup_then_thirty_series(self):
        api = FakeApi()
        (times, exports, reason), _ = run_measure(api)
        posts = self.series_posts(api)
        self.assertEqual(len(posts), 1 + 30)
        self.assertEqual((posts[0][2]["name"], posts[0][2]["n_steps"]),
                         ("Algorithmen R0 binary", 2))
        self.assertTrue(all(c[2]["n_steps"] == 40 for c in posts[1:]))
        self.assertTrue(all(c[3] == run.SERIES_TIMEOUT_S for c in posts))
        self.assertIsNone(reason)
        self.assertEqual((len(times), len(exports)), (30, 30))

    def test_order_and_new_rocket_per_series(self):
        api = FakeApi()
        (times, _, _), _ = run_measure(api)
        self.assertEqual([(t["label"], t["searcher"]) for t in times],
                         [(l, s) for l in LABELS for s in run.SEARCHERS])
        rockets = [c for c in api.calls if c[1] == "/rockets"]
        self.assertEqual(len(rockets), 31)
        self.assertEqual(len({t["rocket_id"] for t in times}), 30)

    def test_targets_from_h_pmax(self):
        api = FakeApi()
        h = h_all()
        run_measure(api, h)
        for c in self.series_posts(api)[1:]:
            label = c[2]["name"].split()[1]
            self.assertEqual((c[2]["param_start"], c[2]["param_stop"]),
                             (0.05 * h[label], 0.95 * h[label]))
            self.assertEqual((c[2]["mode"], c[2]["param_name"]), ("inverse", "target_apogee"))

    def test_three_calls_per_series(self):
        (times, _, _), _ = run_measure(FakeApi())
        self.assertTrue(all(t["aufrufe"] == 3 for t in times))

    def test_times_recorded(self):
        (times, _, _), _ = run_measure(FakeApi())
        for t in times:
            self.assertEqual((t["status"], t["fehler"]), ("201", ""))
            self.assertEqual(float(t["duration_s"]), MARK_DURATION)
            self.assertGreaterEqual(float(t["t_client_s"]), 0.0)
            self.assertEqual(t["file"], f"{t['label']}_{t['searcher']}_serie_{t['series_id']}.csv")

    def test_excluded_rocket_skipped(self):
        (times, _, _), _ = run_measure(FakeApi(), h_all(exclude=("R5",)))
        self.assertEqual(len(times), 27)
        self.assertNotIn("R5", {t["label"] for t in times})

    def test_422_recorded_and_continues(self):
        api = FakeApi(series_status={"Algorithmen R2 interpolation": 422})
        (times, exports, reason), output = run_measure(api)
        self.assertIsNone(reason)
        self.assertEqual(len(times), 30)
        row = times[8]
        self.assertEqual((row["label"], row["searcher"], row["status"]),
                         ("R2", "interpolation", "422"))
        self.assertEqual((row["aufrufe"], row["file"], row["series_id"]), (2, "", ""))
        self.assertIn(MARK_ERROR, row["fehler"])
        self.assertEqual(len(exports), 29)
        self.assertNotIn(MARK_ERROR, output)

    def test_504_is_recorded_and_stops(self):
        api = FakeApi(series_status={"Algorithmen R1 exponential": 504})
        (times, exports, reason), _ = run_measure(api)
        self.assertEqual(len(times), 5)
        self.assertEqual((times[-1]["status"], times[-1]["aufrufe"]), ("504", 2))
        self.assertIn("R1 exponential", reason)
        self.assertEqual(len(exports), 4)

    def test_client_timeout_is_recorded(self):
        api = FakeApi(series_status={"Algorithmen R0 interpolation": TimeoutError("x")})
        (times, _, reason), _ = run_measure(api)
        self.assertEqual(times[-1]["status"], "timeout")
        self.assertIn("R0 interpolation", reason)

    def test_other_errors_abort(self):
        for outcome in (500, 404, ConnectionRefusedError()):
            with self.subTest(outcome=outcome):
                api = FakeApi(series_status={"Algorithmen R3 binary": outcome})
                with self.assertRaises((RuntimeError, ConnectionRefusedError)):
                    run_measure(api)

    def test_warmup_must_succeed(self):
        api = FakeApi(series_status={"Algorithmen R0 binary": 422})
        with self.assertRaisesRegex(RuntimeError, "Aufwaermlauf"):
            run_measure(api)

    def test_warmup_needs_r0(self):
        with self.assertRaisesRegex(RuntimeError, "R0"):
            run_measure(FakeApi(), h_all(exclude=("R0",)))

    def test_no_values_printed(self):
        api = FakeApi(series_status={"Algorithmen R6 binary": 422})
        _, output = run_measure(api)
        for mark in (MARK_APOGEE, MARK_EVALS, str(MARK_DURATION)[:6], str(MARK_H)[:6],
                     MARK_ERROR):
            self.assertNotIn(mark, output)


class Writing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.durchsatz = Path(self.tmp.name) / "durchsatz"
        write_inputs(self.durchsatz)

    def tearDown(self):
        self.tmp.cleanup()

    def main(self, api):
        out = io.StringIO()
        with mock.patch.object(run, "request", api), \
                mock.patch.object(run, "wait_for_api", lambda: None), \
                contextlib.redirect_stdout(out):
            return run.main(self.data, self.durchsatz), out.getvalue()

    def read_times(self):
        with open(self.data / run.TIMES_NAME, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_csv_written_byte_for_byte(self):
        self.assertEqual(self.main(FakeApi())[0], 0)
        rows = self.read_times()
        first = rows[0]
        targets = run.expected_targets(0.05 * MARK_H, 0.95 * MARK_H, 40)
        body = (self.data / first["file"]).read_bytes()
        self.assertEqual(body, fake_csv(int(first["series_id"]), "binary", targets))
        self.assertIn(b"\r\n", body)

    def test_times_file_columns_and_rows(self):
        self.main(FakeApi())
        rows = self.read_times()
        self.assertEqual(list(rows[0]), run.TIMES_COLUMNS)
        self.assertEqual(len(rows), 30)
        self.assertEqual(len(list(self.data.glob("R*_serie_*.csv"))), 30)

    def test_422_written_with_error_text(self):
        code, output = self.main(FakeApi(series_status={"Algorithmen R9 exponential": 422}))
        self.assertEqual(code, 0)
        row = [r for r in self.read_times() if r["status"] == "422"][0]
        self.assertIn(MARK_ERROR, row["fehler"])
        self.assertNotIn(MARK_ERROR, output)
        self.assertEqual(len(list(self.data.glob("R*_serie_*.csv"))), 29)

    def test_existing_times_abort_without_api(self):
        self.data.mkdir()
        (self.data / run.TIMES_NAME).write_text("x")
        api = FakeApi()
        self.assertEqual(self.main(api)[0], 2)
        self.assertEqual(api.calls, [])
        self.assertEqual((self.data / run.TIMES_NAME).read_text(), "x")

    def test_bad_inputs_abort_without_api(self):
        (self.durchsatz / "results" / "monotonie.csv").write_text("label\nR0\n")
        api = FakeApi()
        self.assertEqual(self.main(api)[0], 1)
        self.assertEqual(api.calls, [])
        self.assertFalse(self.data.exists())

    def test_failure_writes_nothing(self):
        api = FakeApi(series_status={"Algorithmen R5 binary": 500})
        self.assertEqual(self.main(api)[0], 1)
        self.assertFalse(self.data.exists())

    def test_504_writes_partial_times_and_returns_3(self):
        api = FakeApi(series_status={"Algorithmen R9 interpolation": 504})
        self.assertEqual(self.main(api)[0], 3)
        rows = self.read_times()
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
                    if "unprocessable" in self.path:
                        self.send_response(422)
                        self.end_headers()
                        self.wfile.write(b'{"detail": [{"msg": "a"}, {"msg": "b"}]}')
                        return
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

    def test_422_body_and_error_text(self):
        with mock.patch.object(run, "API_BASE", self.base):
            status, body, _ = run.post_series("unprocessable", {"n": 1})
        self.assertEqual((status, run.error_text(body)), ("422", "a | b"))

    def test_error_text_without_json(self):
        self.assertEqual(run.error_text(b"<html>kaputt</html>"), "<html>kaputt</html>")

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