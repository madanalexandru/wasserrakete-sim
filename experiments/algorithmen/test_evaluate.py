"""Tests für evaluate.py mit erfundenen Daten.

Kein Test liest die echten Messdaten.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -W error -m unittest discover -s algorithmen -v"
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

LABELS = [f"R{i}" for i in range(10)]
EXPORT_COLUMNS = ["id", "series_id", "target_apogee", "searcher", "search_evaluations",
                  "p0_gauge", "apogee"]


def fake_searches(searcher, offset=0.37):
    """40 Suchen: p* über den Bereich verteilt, Treffer genau nach Vorhersage."""
    rows = []
    for i in range(run.N_TARGETS):
        p = 6e3 + i * 24e3 + offset  # 6 kPa bis 942 kPa, keine Grenze
        target = 10.0 + i
        if searcher == "binary":
            evals = 22
        elif searcher == "exponential":
            evals = evaluate.h2_expected(p)
        else:
            evals = 12
        rows.append({"target": target, "p_star": p, "apogee": target * (1 + 1e-7),
                     "evals": evals})
    return rows


def write_export(path, series_id, searcher, searches):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(EXPORT_COLUMNS)
        for i, s in enumerate(searches):
            w.writerow([i + 1, series_id, repr(s["target"]), searcher, s["evals"],
                        repr(s["p_star"]), repr(s["apogee"])])


def fake_times(labels=LABELS, status=None):
    """Zeitenzeilen wie run.py; status: (label, searcher) -> Status."""
    rows, sid = [], 47
    status = status or {}
    for label in labels:
        for s in run.SEARCHERS:
            st = status.get((label, s), "201")
            rows.append({
                "label": label, "searcher": s, "rocket_id": sid + 16,
                "series_id": sid if st == "201" else "", "n_steps": run.N_TARGETS,
                "status": st, "t_client_s": repr(40.0 + sid % 3), "duration_s": "39.0",
                "aufrufe": 3 if st == "201" else 2,
                "file": f"{label}_{s}_serie_{sid}.csv" if st == "201" else "",
                "fehler": "" if st == "201" else "Suche nicht konvergiert",
            })
            sid += 1
    return rows


def write_times(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.TIMES_COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


def write_world(root, status=None, excluded=()):
    """Erfundene Rohdaten, monotonie.csv und kennzahlen.csv unter root."""
    data, durchsatz, cw = root / "data", root / "durchsatz", root / "cw"
    data.mkdir()
    (durchsatz / "results").mkdir(parents=True)
    (cw / "results").mkdir(parents=True)
    with open(durchsatz / "results" / "monotonie.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["label", "file", "m1", "m2", "abnahmen", "abnahmen_le0", "im_vergleich"])
        for label in LABELS:
            w.writerow([label, f"{label}.csv", "nein", "ja", 6, 6,
                        "nein" if label in excluded else "ja"])
    with open(cw / "results" / "kennzahlen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["label", "h_ref_m", "S_pct"])
        for label in LABELS:
            w.writerow([label, "50.0", "5.0"])
    labels = [l for l in LABELS if l not in excluded]
    rows = fake_times(labels, status)
    write_times(data / run.TIMES_NAME, rows)
    for r in rows:
        if r["status"] == "201":
            write_export(data / r["file"], r["series_id"], r["searcher"],
                         fake_searches(r["searcher"]))
    return data, durchsatz, cw


class Prediction(unittest.TestCase):
    def test_bands(self):
        cases = {1e3 + 2: 18, 50e3: 18, 52e3: 19, 150e3: 21, 300e3: 23, 500e3: 25,
                 900e3: 25}
        for p, n in cases.items():
            self.assertEqual(evaluate.h2_expected(p), n, p)

    def test_boundary_strictly_less_than_one_pa(self):
        self.assertIsNone(evaluate.h2_expected(51e3 + 0.999))
        self.assertIsNone(evaluate.h2_expected(51e3 - 0.999))
        self.assertEqual(evaluate.h2_expected(51e3 + 1.0), 19)
        self.assertEqual(evaluate.h2_expected(51e3 - 1.0), 18)

    def test_all_boundaries(self):
        for g in (1e3, 51e3, 101e3, 201e3, 401e3, 801e3, 1e6):
            self.assertTrue(evaluate.is_boundary(g + 0.5), g)
            self.assertTrue(evaluate.is_boundary(g - 0.5), g)

    def test_table_as_in_note(self):
        self.assertEqual(evaluate.H2_BANDS, [(1e3, 51e3, 18), (51e3, 101e3, 19),
                                             (101e3, 201e3, 21), (201e3, 401e3, 23),
                                             (401e3, 1e6, 25)])
        self.assertEqual(evaluate.H1_BINARY, 22)


class Assess(unittest.TestCase):
    def search(self, apogee=101.0, target=100.0, p=300e3, evals=22):
        return {"target": target, "apogee": apogee, "p_star": p, "evals": evals}

    def test_delta_and_k2_limit(self):
        ok = evaluate.assess(self.search(), "binary", 100.0)  # delta 1 %, S/100 = 1 %
        self.assertEqual(ok["delta_pct"], 1.0)
        self.assertTrue(ok["k2"])
        bad = evaluate.assess(self.search(), "binary", math.nextafter(100.0, 0.0))
        self.assertFalse(bad["k2"])

    def test_delta_below_target(self):
        self.assertEqual(evaluate.assess(self.search(apogee=99.0), "binary", 1.0)["delta_pct"],
                         1.0)

    def test_binary_prediction(self):
        self.assertTrue(evaluate.assess(self.search(evals=22), "binary", 5.0)["treffer"])
        self.assertFalse(evaluate.assess(self.search(evals=21), "binary", 5.0)["treffer"])

    def test_exponential_prediction_and_boundary(self):
        a = evaluate.assess(self.search(evals=23), "exponential", 5.0)
        self.assertEqual((a["vorhersage"], a["treffer"], a["grenzfall"]), (23, True, False))
        b = evaluate.assess(self.search(p=401e3 + 0.2, evals=25), "exponential", 5.0)
        self.assertEqual((b["vorhersage"], b["treffer"], b["grenzfall"]), (None, None, True))

    def test_interpolation_without_prediction(self):
        a = evaluate.assess(self.search(evals=9), "interpolation", 5.0)
        self.assertEqual((a["vorhersage"], a["treffer"]), (None, None))


class Summary(unittest.TestCase):
    def groups(self, interp_evals=12, status=None, t=40.0, calls=3):
        times = [dict(r, t_client=t, aufrufe=calls if r["status"] == "201" else 2)
                 for r in fake_times(status=status)]
        searches = {}
        for r in times:
            if r["status"] == "201":
                found = fake_searches(r["searcher"])
                if r["searcher"] == "interpolation":
                    found = [dict(s, evals=interp_evals) for s in found]
                searches[r["file"]] = found
        return evaluate.evaluate(times, searches, {label: 5.0 for label in LABELS})

    def test_all_met(self):
        s = evaluate.summary(self.groups())
        self.assertEqual((s["serien"], s["k1"], s["suchen"], s["k2"]), (30, 30, 1200, 1200))
        self.assertEqual((s["h1"], s["h2"], s["h3"]), ((400, 400), (400, 400), (10, 10)))
        self.assertEqual((s["zeit"], s["aufwand"], s["h2_grenzfaelle"]), (30, 30, 0))
        self.assertEqual(s["summe"]["binary"], 22 * 400)
        self.assertEqual(s["summe"]["interpolation"], 12 * 400)

    def test_h3_median_must_be_below_22(self):
        self.assertEqual(evaluate.summary(self.groups(interp_evals=22))["h3"], (0, 10))

    def test_h3_uses_median_not_mean(self):
        # 21-mal 10 und 19-mal 40: Median 10 (< 22), Mittelwert 24,25 (>= 22)
        times = [dict(r, t_client=40.0) for r in fake_times()]
        searches = {}
        for r in times:
            found = fake_searches(r["searcher"])
            if r["searcher"] == "interpolation":
                found = [dict(s, evals=10 if i < 21 else 40) for i, s in enumerate(found)]
            searches[r["file"]] = found
        groups = evaluate.evaluate(times, searches, {l: 5.0 for l in LABELS})
        self.assertEqual(evaluate.summary(groups)["h3"], (10, 10))
        self.assertEqual(groups[2]["eval"], (10.0, 10, 40, 970))

    def test_422_counts_against_k1(self):
        s = evaluate.summary(self.groups(status={("R4", "exponential"): "422"}))
        self.assertEqual((s["k1"], s["suchen"], s["h2"][1]), (29, 1160, 360))

    def test_time_threshold_strict(self):
        self.assertEqual(evaluate.summary(self.groups(t=300.0))["zeit"], 0)
        below = math.nextafter(300.0, 0.0)
        self.assertEqual(evaluate.summary(self.groups(t=below))["zeit"], 30)

    def test_boundary_searches_counted_separately(self):
        groups = self.groups()
        exp = [g for g in groups if g["searcher"] == "exponential"][0]
        moved = dict(exp["items"][0], p_star=401e3 + 0.2, evals=25)
        times = [dict(r, t_client=40.0) for r in fake_times()]
        searches = {g["file"]: [{k: s[k] for k in ("target", "p_star", "apogee", "evals")}
                                for s in g["items"]] for g in groups}
        searches[exp["file"]][0] = {k: moved[k] for k in ("target", "p_star", "apogee", "evals")}
        s = evaluate.summary(evaluate.evaluate(times, searches, {l: 5.0 for l in LABELS}))
        self.assertEqual((s["h2_grenzfaelle"], s["h2"]), (1, (399, 399)))

    def test_calls_threshold(self):
        self.assertEqual(evaluate.summary(self.groups(calls=4))["aufwand"], 0)


class Loading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / run.TIMES_NAME

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, rows, labels=LABELS):
        write_times(self.path, rows)
        return evaluate.load_times(self.path, labels)

    def test_valid_with_422(self):
        rows = self.load(fake_times(status={("R2", "binary"): "422"}))
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[6]["status"], "422")

    def test_wrong_order(self):
        rows = fake_times()
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(ValueError, "Reihenfolge"):
            self.load(rows)

    def test_only_included_labels(self):
        with self.assertRaisesRegex(ValueError, "Reihenfolge"):
            self.load(fake_times(), labels=LABELS[:9])

    def test_status_504(self):
        rows = fake_times()
        rows[3]["status"] = "504"
        with self.assertRaisesRegex(ValueError, "Status 504"):
            self.load(rows)

    def test_file_of_422_must_be_empty(self):
        rows = fake_times(status={("R1", "binary"): "422"})
        rows[3]["file"] = "R1_binary_serie_50.csv"
        with self.assertRaisesRegex(ValueError, "Dateiname"):
            self.load(rows)

    def test_wrong_n_steps(self):
        rows = fake_times()
        rows[5]["n_steps"] = 2
        with self.assertRaisesRegex(ValueError, "n_steps"):
            self.load(rows)

    def test_wrong_columns(self):
        self.path.write_text("label,searcher\r\nR0,binary\r\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Spalten"):
            evaluate.load_times(self.path, LABELS)

    def test_export_checks(self):
        path = Path(self.tmp.name) / "x.csv"
        write_export(path, 47, "binary", fake_searches("binary")[:39])
        with self.assertRaisesRegex(ValueError, "Zeilenzahl"):
            evaluate.load_searches(path, "47", "binary")
        write_export(path, 47, "binary", fake_searches("binary"))
        with self.assertRaisesRegex(ValueError, "fremde"):
            evaluate.load_searches(path, "47", "exponential")
        with self.assertRaisesRegex(ValueError, "fremde"):
            evaluate.load_searches(path, "48", "binary")
        self.assertEqual(len(evaluate.load_searches(path, "47", "binary")), 40)


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / "results"

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, **kw):
        data, durchsatz, cw = write_world(self.root, **kw)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = evaluate.main(data, self.out, durchsatz, cw)
        return code, buf.getvalue()

    def read_csv(self, name):
        with open(self.out / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_console_shows_only_file_names(self):
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(text.splitlines(),
                         [f"geschrieben: results/{n}" for n in evaluate.OUTPUTS])

    def test_outputs_exist_and_text_uses_lf(self):
        self.run_main()
        for name in evaluate.OUTPUTS:
            self.assertGreater((self.out / name).stat().st_size, 0, name)
        for name in ("suchen.csv", "algorithmen.csv", "algorithmen.md"):
            self.assertNotIn(b"\r", (self.out / name).read_bytes(), name)

    def test_csv_contents(self):
        self.run_main(status={("R7", "interpolation"): "422"})
        searches = self.read_csv("suchen.csv")
        self.assertEqual(len(searches), 29 * 40)
        self.assertEqual(list(searches[0]), evaluate.SEARCH_COLUMNS)
        groups = self.read_csv("algorithmen.csv")
        self.assertEqual(len(groups), 30)
        g = [r for r in groups if r["status"] == "422"][0]
        self.assertEqual((g["label"], g["suchen"], g["eval_median"], g["k2_erfuellt"]),
                         ("R7", "0", "", ""))

    def test_md_summary(self):
        self.run_main()
        text = (self.out / "algorithmen.md").read_text(encoding="utf-8")
        self.assertIn("K1 (konvergiert): 30 von 30 Serien.", text)
        self.assertIn("K2 (delta <= S/100): 1200 von 1200 Suchen.", text)
        self.assertIn("H1 (binär = 22): 400 von 400 Suchen.", text)
        self.assertIn("H3 (Interpolation, Median < 22): 10 von 10 Raketen.", text)
        self.assertIn("| R0 | 22 (22 bis 22) |", text)

    def test_excluded_rocket(self):
        self.run_main(excluded=("R9",))
        self.assertEqual(len(self.read_csv("algorithmen.csv")), 27)
        text = (self.out / "algorithmen.md").read_text(encoding="utf-8")
        self.assertIn("K1 (konvergiert): 27 von 27 Serien.", text)

    def test_reproducible(self):
        self.run_main()
        first = {n: (self.out / n).read_bytes() for n in evaluate.OUTPUTS}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            evaluate.main(self.root / "data", self.out, self.root / "durchsatz",
                          self.root / "cw")
        self.assertEqual(first, {n: (self.out / n).read_bytes() for n in evaluate.OUTPUTS})


if __name__ == "__main__":
    unittest.main()