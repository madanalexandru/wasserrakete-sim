"""Tests für evaluate.py mit erfundenen Daten.

Kein Test liest die echten Messdaten.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -W error -m unittest discover -s parameterstudie -v"
"""

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

import evaluate
import run

PLAN = run.rockets()
LABELS = [label for label, _ in PLAN]
CONFIGS = dict(PLAN)
EXPORT_COLUMNS = (["id", "series_id", "v_bottle", "v_water0", "p0_gauge", "d_nozzle",
                   "m_empty", "c_w", "d_body"] + evaluate.RESULT_COLUMNS)
MARK = 4242.4242  # auffälliger Ergebniswert: darf nie auf der Konsole stehen


def fake_curve(k):
    """Erfundene Apogäen je Schritt: Maximum innen bei Schritt 20 + k % 30."""
    peak = 20 + k % 30
    return [MARK - 0.01 * (i - peak) ** 2 + 0.001 * k for i in range(run.N_STEPS)]


def write_export(path, series_id, config, apogees, cells=None):
    """Export wie die API (CRLF); cells: (Schritt, Spalte) -> Text."""
    cells = cells or {}
    water = run.expected_water(config, run.N_STEPS)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(EXPORT_COLUMNS)
        for i, (v, h) in enumerate(zip(water, apogees)):
            row = {"id": i + 1, "series_id": series_id, "v_water0": repr(v),
                   **{c: repr(config[c]) for c in run.CONFIG_COLUMNS},
                   **{c: "1.5" for c in evaluate.RESULT_COLUMNS}, "apogee": repr(h)}
            for (step, col), text in cells.items():
                if step == i:
                    row[col] = text
            w.writerow([row[c] for c in EXPORT_COLUMNS])


def make_data(data, status=None, stop_at=None, curves=None, cells=None, t_lauf=2.5):
    """Erfundener Messordner. status: Label -> 422/504/timeout; stop_at: letzte Zeile."""
    data.mkdir(parents=True)
    status, curves, cells = status or {}, curves or {}, cells or {}
    rows, sid = [], 78
    for k, (label, config) in enumerate(PLAN):
        st = status.get(label, "201")
        row = {"label": label, "rocket_id": sid + 36, "series_id": "", "n_steps": run.N_STEPS,
               "status": st, "fehlertext": "x" if st == "422" else "", "t_client_s": "2.0",
               "t_lauf_s": repr(t_lauf), "duration_s": "", "aufrufe": 3 if st == "201" else 2,
               "file": ""}
        if st == "201":
            row["series_id"] = sid
            row["duration_s"] = "1.9"
            row["file"] = f"{label}_serie_{sid}.csv"
            write_export(data / row["file"], sid, config, curves.get(label, fake_curve(k)),
                         cells.get(label))
        rows.append(row)
        sid += 1
        if label == stop_at:
            break
    with open(data / run.RUNS_NAME, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.RUNS_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return rows


def run_main(data, out):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = evaluate.main(data, out)
    return code, buf.getvalue()


def evaluated(tmp, **kwargs):
    data = Path(tmp) / "data"
    make_data(data, **kwargs)
    runs = evaluate.load_runs(data / run.RUNS_NAME)
    points = {label: evaluate.load_points(data / r["file"], r["series_id"], CONFIGS[label])
              for label, r in runs.items() if r["status"] == "201"}
    rockets = evaluate.evaluate(runs, points)
    return rockets, evaluate.summary(rockets)


class Rules(unittest.TestCase):
    def test_fill_pct(self):
        self.assertEqual([evaluate.fill_pct(0), evaluate.fill_pct(90)], [5, 95])
        self.assertEqual(evaluate.N_POINTS, 4914)

    def test_is_finite_cell(self):
        for cell, want in [("1.5", True), ("0", True), ("-3e-08", True), ("", False),
                           ("nan", False), ("inf", False), ("-inf", False), ("abc", False)]:
            with self.subTest(cell=cell):
                self.assertEqual(evaluate.is_finite_cell(cell), want)

    def rocket(self, apogees, valid=None):
        valid = valid or [True] * len(apogees)
        points = [(v, h if v else None) for v, h in zip(valid, apogees)]
        row = {"status": "201", "t_client": 1.0, "t_lauf": 1.1, "aufrufe": 3}
        return evaluate.evaluate_rocket("X", CONFIGS[LABELS[0]], row, points)

    def test_max_and_tie_takes_smaller_fill(self):
        h = [1.0] * 91
        h[30] = h[40] = 9.0
        r = self.rocket(h)
        self.assertEqual((r["f_max"], r["h_max"], r["innen"]), (35, 9.0, True))

    def test_innen_at_edges(self):
        for i, innen in [(0, False), (90, False), (1, True), (89, True)]:
            with self.subTest(i=i):
                h = [1.0] * 91
                h[i] = 2.0
                self.assertEqual(self.rocket(h)["innen"], innen)

    def test_invalid_points_excluded(self):
        h = [1.0] * 91
        h[50] = 9.0
        valid = [True] * 91
        valid[50] = False
        r = self.rocket(h, valid)
        self.assertEqual((r["valid"], r["f_max"], r["curve"][50]), (90, 5, None))

    def test_nonpositive_apogee_is_valid_and_counted(self):
        h = [1.0] * 91
        h[0], h[1] = 0.0, -3e-8
        r = self.rocket(h)
        self.assertEqual((r["valid"], r["le0"]), (91, 2))

    def test_no_export(self):
        r = evaluate.evaluate_rocket("X", CONFIGS[LABELS[0]], None, None)
        self.assertEqual((r["status"], r["valid"], r["f_max"], r["innen"]),
                         ("nicht gemessen", 0, None, None))


class Evaluate(unittest.TestCase):
    def test_all_valid_kpi_met(self):
        with tempfile.TemporaryDirectory() as tmp:
            rockets, s = evaluated(tmp)
        self.assertEqual((s["valid"], s["points"], s["kpi"]), (4914, 4914, True))
        self.assertEqual((s["innen"], s["with_max"], s["le0"]), (54, 54, 0))
        self.assertEqual(s["status"]["201"], 54)

    def test_peak_found_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rockets, _ = evaluated(tmp)
        for k, r in enumerate(rockets):
            with self.subTest(label=r["label"]):
                self.assertEqual(r["f_max"], 5 + 20 + k % 30)

    def test_one_bad_cell_misses_kpi(self):
        for text in ("", "nan", "inf", "-inf"):
            for col in ("apogee", "water_rest"):
                with self.subTest(text=text, col=col), tempfile.TemporaryDirectory() as tmp:
                    _, s = evaluated(tmp, cells={LABELS[7]: {(3, col): text}})
                    self.assertEqual((s["valid"], s["kpi"]), (4913, False))

    def test_422_counts_91_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            rockets, s = evaluated(tmp, status={LABELS[5]: "422"})
        self.assertEqual((s["valid"], s["kpi"], s["status"]["422"]), (4914 - 91, False, 1))
        self.assertEqual((rockets[5]["f_max"], s["with_max"]), (None, 53))

    def test_stop_counts_rest_as_not_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            rockets, s = evaluated(tmp, status={LABELS[9]: "504"}, stop_at=LABELS[9])
        self.assertEqual(s["valid"], 9 * 91)
        self.assertEqual(s["points"], 4914)
        self.assertEqual((s["status"]["504"], s["status"]["nicht gemessen"]), (1, 44))
        self.assertEqual(s["flights"], 9 * 91)

    def test_nonpositive_counted(self):
        curve = fake_curve(0)
        curve[0], curve[1] = 0.0, -1e-3
        with tempfile.TemporaryDirectory() as tmp:
            _, s = evaluated(tmp, curves={LABELS[0]: curve})
        self.assertEqual((s["le0"], s["le0_rockets"], s["kpi"]), (2, 1, True))

    def test_times_and_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, s = evaluated(tmp, t_lauf=2.5)
        self.assertEqual(s["t_lauf"], 54 * 2.5)
        self.assertEqual(s["t_client"], 54 * 2.0)
        self.assertEqual(s["aufrufe"], 162)
        self.assertEqual(s["rate"], 4914 / (54 * 2.5))

    def test_figure_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            rockets, _ = evaluated(tmp)
        panels = evaluate.figure_rockets(rockets)
        self.assertEqual([b for b, _ in panels], ["F10", "F15", "F20"])
        for b, lines in panels:
            self.assertEqual([r["label"] for _, r in lines],
                             [f"{b}-{p}-D22-M150" for p in ("P3", "P5", "P7")])


class LoadRuns(unittest.TestCase):
    def edit(self, change):
        """Erfundene laeufe.csv ändern; liefert den Pfad."""
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name) / "data"
        rows = make_data(data)
        change(rows)
        with open(data / run.RUNS_NAME, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=run.RUNS_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        return data / run.RUNS_NAME

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def test_valid_complete(self):
        self.assertEqual(len(evaluate.load_runs(self.edit(lambda rows: None))), 54)

    def test_errors(self):
        def swap(rows):
            rows[0], rows[1] = rows[1], rows[0]

        def drop_last(rows):
            rows.pop()

        def stop_in_middle(rows):
            rows[3].update(status="504", series_id="", file="")

        def unknown(rows):
            rows[0]["status"] = "500"

        def wrong_file(rows):
            rows[0]["file"] = "x.csv"

        def file_for_422(rows):
            rows[0]["status"] = "422"

        def steps(rows):
            rows[0]["n_steps"] = 90

        def times(rows):
            rows[0]["t_lauf_s"] = "1.0"

        cases = [(swap, "Reihenfolge"), (drop_last, "ohne Abbruchstatus"),
                 (stop_in_middle, "nicht in der letzten Zeile"), (unknown, "unbekannter Status"),
                 (wrong_file, "Dateiname"), (file_for_422, "Dateiname"), (steps, "n_steps"),
                 (times, "Zeiten")]
        for change, message in cases:
            with self.subTest(change=change.__name__):
                path = self.edit(change)
                with self.assertRaisesRegex(ValueError, message):
                    evaluate.load_runs(path)
                self.tmp.cleanup()

    def test_wrong_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / run.RUNS_NAME).write_text("label,status\nF10-P3-D15-M100,201\n")
            with self.assertRaises(ValueError):
                evaluate.load_runs(data / run.RUNS_NAME)

    def test_stop_in_last_row_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            make_data(data, status={LABELS[2]: "timeout"}, stop_at=LABELS[2])
            self.assertEqual(len(evaluate.load_runs(data / run.RUNS_NAME)), 3)

    def test_export_structure_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            rows = make_data(data, cells={LABELS[0]: {(4, "v_water0"): "1e-4"}})
            with self.assertRaises(RuntimeError):
                evaluate.load_points(data / rows[0]["file"], rows[0]["series_id"],
                                     CONFIGS[LABELS[0]])


class Main(unittest.TestCase):
    def test_console_only_file_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_data(Path(tmp) / "data")
            code, out = run_main(Path(tmp) / "data", Path(tmp) / "results")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(),
                         [f"geschrieben: results/{name}" for name in evaluate.OUTPUTS])

    def test_outputs_and_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_data(Path(tmp) / "data")
            out = Path(tmp) / "results"
            run_main(Path(tmp) / "data", out)
            for name in evaluate.OUTPUTS:
                self.assertTrue((out / name).stat().st_size > 0, name)
            for name in ("parameterstudie.csv", "parameterstudie.md"):
                self.assertNotIn(b"\r", (out / name).read_bytes())

    def test_csv_contents(self):
        curve = fake_curve(0)
        with tempfile.TemporaryDirectory() as tmp:
            make_data(Path(tmp) / "data", status={LABELS[1]: "422"})
            out = Path(tmp) / "results"
            run_main(Path(tmp) / "data", out)
            with open(out / "parameterstudie.csv", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), evaluate.ROCKET_COLUMNS)
        self.assertEqual(len(rows), 54)
        first = rows[0]
        self.assertEqual((first["label"], first["status"], first["punkte_gueltig"],
                          first["f_max_pct"], first["innen"]),
                         (LABELS[0], "201", "91", "25", "ja"))
        self.assertEqual(float(first["h_max_m"]), max(curve))
        self.assertEqual(first["h_max_m"], repr(max(curve)))
        self.assertEqual((rows[1]["status"], rows[1]["punkte_gueltig"], rows[1]["f_max_pct"],
                          rows[1]["innen"], rows[1]["h_max_m"]), ("422", "0", "", "", ""))

    def test_md_kpi_line(self):
        for status, word in ((None, "erfüllt"), ({LABELS[1]: "422"}, "NICHT erfüllt")):
            with self.subTest(word=word), tempfile.TemporaryDirectory() as tmp:
                make_data(Path(tmp) / "data", status=status)
                out = Path(tmp) / "results"
                run_main(Path(tmp) / "data", out)
                text = (out / "parameterstudie.md").read_text(encoding="utf-8")
                kpi = [line for line in text.splitlines() if line.startswith("KPI")][0]
                self.assertTrue(kpi.endswith(f"Schwelle 100 %: {word}."), kpi)
                if status is None:
                    self.assertIn("A = 4914 von 4914 Punkten gültig (100,00 %)", kpi)

    def test_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            make_data(data)
            run_main(data, Path(tmp) / "a")
            run_main(data, Path(tmp) / "b")
            for name in evaluate.OUTPUTS:
                with self.subTest(name=name):
                    self.assertEqual((Path(tmp) / "a" / name).read_bytes(),
                                     (Path(tmp) / "b" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()