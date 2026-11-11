"""Tests für evaluate.py mit erfundenen Daten.

Kein Test liest die echten Messdaten. Die Spalten der erfundenen werte.csv
kommen aus run.py, damit Mess- und Auswerte-Skript zusammenpassen.

Start (PowerShell, im Repo-Ordner): wie test_run.py (gemeinsamer Lauf)
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\\backend:/backend:ro" -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python -W error -m unittest discover -s ereignissuche -v
"""

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

import evaluate
import run

S_FAKE = {f"R{i}": 2.0 + 0.1 * i for i in range(10)}  # erfunden, in %
H0 = 100.0


def fake_row(label, variant, apogee, bitgleich=None, w=(23, "ja"), f=(25, "ja")):
    name, water_cls, free_cls = run.VARIANTS[variant]
    row = {c: "" for c in run.COLUMNS}
    row.update({
        "label": label, "variante": variant, "name": name,
        "wasser": water_cls.__name__, "freiflug": free_cls.__name__,
        "apogee": repr(apogee), "wasser_auswertungen": w[0], "wasser_konvergiert": w[1],
        "freiflug_auswertungen": f[0], "freiflug_konvergiert": f[1],
        "bitgleich": ("ja" if variant == "V0" else "") if bitgleich is None else bitgleich,
    })
    if water_cls is run.StepEnd:
        row["wasser_auswertungen"], row["wasser_konvergiert"] = 0, "keine Suche"
    if free_cls is run.StepEnd:
        row["freiflug_auswertungen"], row["freiflug_konvergiert"] = 0, "keine Suche"
    return row


def write_fake(data_dir, deltas=None, not_equal=(), v1=None, rows_hook=None):
    """deltas: {(Rakete, Variante): relative Abweichung}; v1: {Rakete: (w, f)}."""
    deltas = deltas or {}
    v1 = v1 or {}
    rows = []
    for label in evaluate.LABELS:
        for variant in run.VARIANTS:
            h = H0 * (1 + deltas.get((label, variant), 0.0))
            kwargs = {}
            if variant == "V0" and label in not_equal:
                kwargs["bitgleich"] = "nein"
            if variant == "V1":
                kwargs["w"], kwargs["f"] = v1.get(label, ((12, "ja"), (9, "ja")))
            rows.append(fake_row(label, variant, h, **kwargs))
    if rows_hook:
        rows = rows_hook(rows)
    data_dir.mkdir(parents=True)
    with open(data_dir / evaluate.VALUES_NAME, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=run.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_kennzahlen(cw_dir, S=None):
    (cw_dir / "results").mkdir(parents=True)
    with open(cw_dir / "results" / "kennzahlen.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["label", "S_pct"])
        for label, s in (S or S_FAKE).items():
            writer.writerow([label, repr(s)])


class Consistency(unittest.TestCase):
    def test_labels_and_variants_match_run(self):
        self.assertEqual(evaluate.LABELS, [label for label, _ in run.rockets()])
        self.assertEqual(evaluate.VARIANTS, list(run.VARIANTS))

    def test_delta_variants_as_in_note(self):
        self.assertEqual(evaluate.DELTAS, {"E": "V2", "W": "V3", "A": "V4"})
        self.assertEqual(run.VARIANTS["V2"][1:], (run.StepEnd, run.StepEnd))
        self.assertIs(run.VARIANTS["V3"][1], run.StepEnd)
        self.assertIs(run.VARIANTS["V4"][2], run.StepEnd)


class Rules(unittest.TestCase):
    def test_delta_signed_percent(self):
        self.assertAlmostEqual(evaluate.delta_pct(101.0, 100.0), 1.0, places=12)
        self.assertAlmostEqual(evaluate.delta_pct(99.0, 100.0), -1.0, places=12)

    def test_classify_uses_absolute_value_and_ge(self):
        self.assertEqual(evaluate.classify(0.02, 0.02), evaluate.WIRKSAM)
        self.assertEqual(evaluate.classify(-0.03, 0.02), evaluate.WIRKSAM)
        self.assertEqual(evaluate.classify(0.019, 0.02), evaluate.VERNACHLAESSIGBAR)
        self.assertEqual(evaluate.classify(-0.019, 0.02), evaluate.VERNACHLAESSIGBAR)

    def test_wording_as_in_note(self):
        self.assertEqual(evaluate.VERNACHLAESSIGBAR, "für das Apogäum vernachlässigbar")


class Evaluate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"

    def tearDown(self):
        self.tmp.cleanup()

    def results(self, **kwargs):
        write_fake(self.data, **kwargs)
        return evaluate.evaluate(self.data, S_FAKE)

    def test_deltas_recovered_with_sign(self):
        res = self.results(deltas={("R1", "V2"): 3e-4, ("R1", "V3"): 5e-4,
                                   ("R1", "V4"): -2e-6})
        r = res[1]
        self.assertAlmostEqual(r["delta"]["E"], 3e-2, delta=1e-12)
        self.assertAlmostEqual(r["delta"]["W"], 5e-2, delta=1e-12)
        self.assertAlmostEqual(r["delta"]["A"], -2e-4, delta=1e-12)

    def test_classification_against_S_over_100(self):
        # S(R1) = 2,1 % -> Schwelle 0,021 %; 3e-4 relativ = 0,03 % -> wirksam
        res = self.results(deltas={("R1", "V2"): 3e-4, ("R1", "V4"): -2e-6})
        r = res[1]
        self.assertAlmostEqual(r["schwelle"], 0.021, places=12)
        self.assertEqual(r["klasse"]["E"], evaluate.WIRKSAM)
        self.assertEqual(r["klasse"]["A"], evaluate.VERNACHLAESSIGBAR)
        s = evaluate.summary(res)
        self.assertEqual((s["n"], s["wirksam"]["E"], s["wirksam"]["A"]), (10, 1, 0))

    def test_negative_large_delta_is_effective(self):
        res = self.results(deltas={("R0", "V2"): -1e-3})
        self.assertEqual(res[0]["klasse"]["E"], evaluate.WIRKSAM)

    def test_not_identical_rocket_not_evaluated(self):
        res = self.results(deltas={("R4", "V2"): 1e-2}, not_equal=("R4",))
        r = res[4]
        self.assertFalse(r["auswertbar"])
        self.assertEqual((r["delta"], r["klasse"]), ({}, {}))
        s = evaluate.summary(res)
        self.assertEqual((s["n"], s["na"], s["wirksam"]["E"]), (9, 1, 0))

    def test_evaluation_statistics(self):
        v1 = {f"R{i}": ((10 + i, "ja"), (5, "ja")) for i in range(10)}
        s = evaluate.summary(self.results(v1=v1))
        self.assertEqual(s["eval"][("wasser", "binaer")], (23, 23, 23, 230))
        self.assertEqual(s["eval"][("wasser", "interpolation")], (14.5, 10, 19, 145))
        self.assertEqual(s["eval"][("freiflug", "interpolation")], (5, 5, 5, 50))
        self.assertEqual(s["konv"], {"wasser": 10, "freiflug": 10})

    def test_not_converged_and_no_freeflight(self):
        v1 = {"R2": ((40, "nein"), (0, "kein Freiflug"))}
        res = self.results(v1=v1)
        self.assertIsNone(res[2]["eval"][("freiflug", "interpolation")])
        s = evaluate.summary(res)
        self.assertEqual(s["konv"], {"wasser": 9, "freiflug": 9})
        self.assertEqual(s["eval"][("freiflug", "interpolation")][3], 9 * 9)

    def test_wrong_order_raises(self):
        def swap(rows):
            rows[0], rows[1] = rows[1], rows[0]
            return rows
        write_fake(self.data, rows_hook=swap)
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, S_FAKE)

    def test_missing_bitgleich_raises(self):
        def blank(rows):
            rows[0]["bitgleich"] = ""
            return rows
        write_fake(self.data, rows_hook=blank)
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, S_FAKE)

    def test_bitgleich_outside_v0_raises(self):
        def mark(rows):
            rows[2]["bitgleich"] = "ja"
            return rows
        write_fake(self.data, rows_hook=mark)
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, S_FAKE)

    def test_missing_threshold_raises(self):
        write_fake(self.data)
        S = dict(S_FAKE)
        del S["R7"]
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, S)


class Output(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data, self.out, self.cw = root / "data", root / "results", root / "cw"
        write_kennzahlen(self.cw)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, **kwargs):
        write_fake(self.data, **kwargs)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = evaluate.main(self.data, self.out, self.cw)
        return code, out.getvalue()

    def test_files_and_console(self):
        code, out = self.run_main(deltas={("R1", "V2"): 3e-4})
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(),
                         [f"geschrieben: results/{n}" for n in evaluate.OUTPUTS])

    def test_csv_columns_and_values(self):
        self.run_main(deltas={("R1", "V2"): 3e-4}, not_equal=("R5",))
        raw = (self.out / "ereignissuche.csv").read_bytes()
        self.assertNotIn(b"\r", raw)
        with open(self.out / "ereignissuche.csv", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(list(rows[0]), evaluate.COLUMNS)
        self.assertEqual(len(rows), 10)
        self.assertAlmostEqual(float(rows[1]["delta_E_pct"]), 3e-2, delta=1e-12)
        self.assertEqual(rows[1]["klasse_E"], evaluate.WIRKSAM)
        self.assertEqual((rows[5]["auswertbar"], rows[5]["delta_E_pct"]), ("nein", ""))

    def test_md_content(self):
        self.run_main(deltas={("R1", "V2"): 3e-4, ("R1", "V4"): -2e-6}, not_equal=("R5",))
        md = (self.out / "ereignissuche.md").read_text(encoding="utf-8")
        self.assertIn("Auswertbar (V0 bitgleich zu simulate_flight): 9 von 10; "
                      "nicht auswertbar: 1.", md)
        self.assertIn("Delta_E (Kennzahl, V2 Schrittende in beiden Phasen): wirksam bei "
                      "1 von 9 Raketen.", md)
        self.assertIn("| R1 | +3,00e-02 | +0,00e+00 | -2,00e-04 | 2,10e-02 | wirksam |", md)
        self.assertIn("| R5 | n. a. | n. a. | n. a. | 2,50e-02 | n. a. (V0 nicht bitgleich) |",
                      md)
        self.assertIn("| Wasser-Ende | 23 (23 bis 23) | 12 (12 bis 12) | 10 von 10 |", md)


if __name__ == "__main__":
    unittest.main()