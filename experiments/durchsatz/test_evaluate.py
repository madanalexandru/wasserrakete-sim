"""Tests für evaluate.py mit erfundenen Daten.

Kein Test liest die echten Messdaten.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -W error -m unittest discover -s durchsatz -v
"""

import contextlib
import csv
import io
import math
import tempfile
import unittest
from pathlib import Path

import evaluate
import run

P0 = run.expected_p0(run.SERIES["n_steps"])


def fake_times(t_client=50.0, duration=40.0, aufrufe=3):
    """Gültige Zeitenzeilen wie von run.py (D1 bis D3, R0 bis R9)."""
    rows, sid = [], 100
    for p in range(1, run.PASSES + 1):
        for label in evaluate.LABELS:
            rows.append({
                "label": label, "durchgang": p, "rocket_id": sid + 500, "series_id": sid,
                "n_steps": run.SERIES["n_steps"], "status": "201",
                "t_client_s": repr(t_client), "duration_s": repr(duration),
                "aufrufe": aufrufe, "file": f"{label}_serie_{sid}.csv" if p == 1 else "",
            })
            sid += 1
    return rows


def write_times(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=run.TIMES_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def write_export(path, series_id, apogees, p0=P0):
    """Export mit CRLF wie die API (nur die gelesenen Spalten)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\r\n")
        writer.writerow(["id", "series_id", "p0_gauge", "apogee"])
        for i, (p, h) in enumerate(zip(p0, apogees)):
            writer.writerow([i + 1, series_id, repr(p), repr(h)])


def rising():
    return [0.1 * (i + 1) for i in range(len(P0))]


def with_ground_noise():
    """Wie vor dem Abheben: 0,0 und knapp negativ, danach streng steigend."""
    return [0.0, -3e-8, -3e-8] + [0.1 * (i + 1) for i in range(len(P0) - 3)]


class Monotonicity(unittest.TestCase):
    def test_strictly_rising(self):
        m = evaluate.monotonicity([1.0, 2.0, 3.0])
        self.assertEqual((m["m1"], m["m2"], m["abnahmen"], m["im_vergleich"]),
                         (True, True, 0, True))

    def test_drop_below_zero_only_is_kept(self):
        m = evaluate.monotonicity([0.0, -3e-8, -3e-8, 0.5, 1.0])
        self.assertEqual((m["m1"], m["m2"], m["abnahmen"], m["abnahmen_le0"]),
                         (False, True, 1, 1))
        self.assertTrue(m["im_vergleich"])

    def test_equal_values_below_zero_are_no_drop(self):
        m = evaluate.monotonicity([0.0, 0.0, 1.0])
        self.assertEqual((m["m1"], m["m2"]), (True, True))

    def test_drop_after_first_positive_excludes(self):
        m = evaluate.monotonicity([0.0, 1.0, 0.9, 2.0])
        self.assertEqual((m["m1"], m["m2"], m["abnahmen_le0"], m["im_vergleich"]),
                         (False, False, 0, False))

    def test_drop_from_positive_to_negative_is_not_le0(self):
        m = evaluate.monotonicity([0.0, 1e-6, -1e-9, 1.0])
        self.assertEqual((m["m2"], m["abnahmen"], m["abnahmen_le0"]), (False, 1, 0))

    def test_plateau_after_first_positive_excludes(self):
        m = evaluate.monotonicity([0.0, 1.0, 1.0, 2.0])
        self.assertEqual((m["m1"], m["m2"], m["im_vergleich"]), (True, False, False))

    def test_smallest_step_counts_as_rising(self):
        m = evaluate.monotonicity([0.0, 1.0, math.nextafter(1.0, 2.0)])
        self.assertTrue(m["m2"])

    def test_no_positive_apogee_excludes(self):
        m = evaluate.monotonicity([0.0, -1e-9, -2e-9])
        self.assertEqual((m["m2"], m["im_vergleich"]), (False, False))


class Throughput(unittest.TestCase):
    def rows(self, t, d, calls=(3, 3, 3)):
        return [{"label": label, "t_client": t[i], "duration": d[i], "aufrufe": calls[i]}
                for i in range(3) for label in evaluate.LABELS]

    def test_median_min_max(self):
        r = evaluate.throughput(self.rows([10.0, 40.0, 20.0], [8.0, 4.0, 5.0]))[0]
        self.assertEqual(r["t_client"], (20.0, 10.0, 40.0))
        self.assertEqual(r["d_client"], (50.0, 25.0, 100.0))
        self.assertEqual(r["d_server"], (200.0, 125.0, 250.0))
        self.assertEqual(r["durchgaenge"], 3)

    def test_time_threshold_is_strict(self):
        below = math.nextafter(300.0, 0.0)
        ok = evaluate.throughput(self.rows([below] * 3, [1.0] * 3))[0]
        bad = evaluate.throughput(self.rows([below, 300.0, below], [1.0] * 3))[0]
        self.assertTrue(ok["zeit_erfuellt"])
        self.assertFalse(bad["zeit_erfuellt"])

    def test_calls_threshold(self):
        ok = evaluate.throughput(self.rows([1.0] * 3, [1.0] * 3, (3, 3, 3)))[0]
        bad = evaluate.throughput(self.rows([1.0] * 3, [1.0] * 3, (3, 4, 3)))[0]
        self.assertEqual((ok["aufwand_erfuellt"], bad["aufwand_erfuellt"]), (True, False))
        self.assertEqual(bad["aufrufe_max"], 4)

    def test_summary_counts_every_series(self):
        rows = self.rows([1.0, 300.0, 1.0], [1.0] * 3, (3, 3, 4))
        self.assertEqual(evaluate.summary(rows), {"serien": 30, "zeit_ok": 20, "aufwand_ok": 20})


class LoadTimes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / run.TIMES_NAME

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, rows):
        write_times(self.path, rows)
        return evaluate.load_times(self.path)

    def test_valid(self):
        rows = self.load(fake_times())
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]["file"], "R0_serie_100.csv")

    def test_missing_row(self):
        with self.assertRaisesRegex(ValueError, "Reihenfolge"):
            self.load(fake_times()[:-1])

    def test_wrong_order(self):
        rows = fake_times()
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(ValueError, "Reihenfolge"):
            self.load(rows)

    def test_status_504(self):
        rows = fake_times()
        rows[5]["status"] = "504"
        with self.assertRaisesRegex(ValueError, "Status 504"):
            self.load(rows)

    def test_wrong_n_steps(self):
        rows = fake_times()
        rows[3]["n_steps"] = 10
        with self.assertRaisesRegex(ValueError, "n_steps"):
            self.load(rows)

    def test_zero_time(self):
        rows = fake_times()
        rows[7]["duration_s"] = "0.0"
        with self.assertRaisesRegex(ValueError, "nicht positiv"):
            self.load(rows)

    def test_file_in_later_pass(self):
        rows = fake_times()
        rows[12]["file"] = "R2_serie_112.csv"
        with self.assertRaisesRegex(ValueError, "Dateiname"):
            self.load(rows)

    def test_duplicate_series(self):
        rows = fake_times()
        rows[29]["series_id"] = rows[28]["series_id"]
        with self.assertRaisesRegex(ValueError, "doppelt"):
            self.load(rows)

    def test_wrong_columns(self):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            f.write("label,durchgang\r\nR0,1\r\n")
        with self.assertRaisesRegex(ValueError, "Spalten"):
            evaluate.load_times(self.path)


class LoadApogees(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "R0_serie_100.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid(self):
        write_export(self.path, 100, rising())
        self.assertEqual(evaluate.load_apogees(self.path, "100"), rising())

    def test_too_few_rows(self):
        write_export(self.path, 100, rising()[:-1])
        with self.assertRaisesRegex(ValueError, "Zeilen"):
            evaluate.load_apogees(self.path, "100")

    def test_foreign_series(self):
        write_export(self.path, 101, rising())
        with self.assertRaisesRegex(ValueError, "fremder"):
            evaluate.load_apogees(self.path, "100")

    def test_wrong_pressures(self):
        write_export(self.path, 100, rising(), p0=P0[:-1] + [P0[-1] + 1.0])
        with self.assertRaisesRegex(ValueError, "Startdrücke"):
            evaluate.load_apogees(self.path, "100")


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.out = Path(self.tmp.name) / "results"
        self.data.mkdir()
        rows = fake_times()
        write_times(self.data / run.TIMES_NAME, rows)
        for r in rows[:10]:
            h = with_ground_noise() if r["label"] == "R3" else rising()
            if r["label"] == "R7":
                h[500] = h[499]  # Plateau nach dem Abheben
            write_export(self.data / r["file"], r["series_id"], h)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = evaluate.main(self.data, self.out)
        return code, buf.getvalue()

    def read_csv(self, name):
        with open(self.out / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_console_shows_only_file_names(self):
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(text.splitlines(),
                         [f"geschrieben: results/{n}" for n in evaluate.OUTPUTS])

    def test_outputs_use_lf(self):
        self.run_main()
        for name in evaluate.OUTPUTS:
            self.assertNotIn(b"\r", (self.out / name).read_bytes(), name)

    def test_monotonie_csv(self):
        self.run_main()
        mono = {r["label"]: r for r in self.read_csv("monotonie.csv")}
        self.assertEqual(list(mono), evaluate.LABELS)
        self.assertEqual(mono["R0"]["im_vergleich"], "ja")
        self.assertEqual((mono["R3"]["m1"], mono["R3"]["m2"], mono["R3"]["abnahmen_le0"],
                          mono["R3"]["im_vergleich"]), ("nein", "ja", "1", "ja"))
        self.assertEqual((mono["R7"]["m1"], mono["R7"]["im_vergleich"]), ("ja", "nein"))
        self.assertEqual(mono["R0"]["file"], "R0_serie_100.csv")

    def test_durchsatz_csv_full_precision(self):
        self.run_main()
        r = self.read_csv("durchsatz.csv")[0]
        self.assertEqual(float(r["d_client_median"]), 1000 / 50.0)
        self.assertEqual(float(r["d_server_max"]), 1000 / 40.0)
        self.assertEqual((r["zeit_erfuellt"], r["aufwand_erfuellt"]), ("ja", "ja"))

    def test_md_summary_and_comma(self):
        self.run_main()
        text = (self.out / "durchsatz.md").read_text(encoding="utf-8")
        self.assertIn("KPI Zeit: 30 von 30 Serien", text)
        self.assertIn("KPI Aufwand: 30 von 30 Serien", text)
        self.assertIn("| R0 | 50,0 (50,0 bis 50,0) | 20,0 (20,0 bis 20,0) |", text)

    def test_reproducible(self):
        self.run_main()
        first = {n: (self.out / n).read_bytes() for n in evaluate.OUTPUTS}
        self.run_main()
        self.assertEqual(first, {n: (self.out / n).read_bytes() for n in evaluate.OUTPUTS})


if __name__ == "__main__":
    unittest.main()