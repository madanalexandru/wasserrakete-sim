"""Tests für evaluate.py mit erfundenen Testdaten (nicht die Messung).

Start (PowerShell, im Repo-Ordner; zusammen mit test_run.py):
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\\backend:/backend:ro" -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python -W error -m unittest discover -s exponent -v
"""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import evaluate


def make(tmp, factor=1.10):
    values = tmp / "werte.csv"
    with open(values, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["label", "beta", "apogee_m"])
        for label in evaluate.LABELS:
            w.writerow([label, "1.4", "100.0"])
            for beta, fac in (("1.17", factor), ("1.2", 1.05), ("1.22", 1.01)):
                w.writerow([label, beta, repr(100.0 * fac)])
    ref = tmp / "ref.csv"
    with open(ref, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["label", "S_pct"])
        for i, label in enumerate(evaluate.LABELS):
            w.writerow([label, "3.0" if i % 2 else "7.0"])
    return values, ref


class TestAuswertung(unittest.TestCase):
    def test_delta_und_zaehlung(self):
        with tempfile.TemporaryDirectory() as tmp:
            values, ref = make(Path(tmp))
            rows, summary = evaluate.evaluate(evaluate.load_values(values),
                                              evaluate.load_thresholds([ref]))
        by = {s["beta"]: s for s in summary}
        self.assertAlmostEqual(by[1.17]["max"], 10.0, places=9)
        self.assertEqual(by[1.17]["n_ueber_S"], 14)   # 10 % > 3 und > 7
        self.assertEqual(by[1.2]["n_ueber_S"], 7)     # 5 % > 3, nicht > 7
        self.assertEqual(by[1.22]["n_ueber_S"], 0)
        self.assertEqual(len(rows), 14 * 3)

    def test_fehlende_rakete_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            evaluate.evaluate({("R0", 1.4): 1.0, ("R0", 1.2): 1.1}, {"R0": 1.0})

    def test_ausgabedateien_ohne_werte_auf_der_konsole(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            values, ref = make(Path(tmp))
            with redirect_stdout(io.StringIO()) as s:
                self.assertEqual(evaluate.main(Path(tmp), Path(out), [ref]), 0)
            self.assertNotIn("10,00", s.getvalue())
            md = (Path(out) / "exponent.md").read_text(encoding="utf-8")
            self.assertIn("| 1,17 | 10,00 % | 10,00 % | 14 von 14 |", md)
            self.assertIn("| R0 | 7,00 % | 10,00 % | 5,00 % | 1,00 % |", md)
            with open(Path(out) / "exponent.csv", encoding="utf-8") as f:
                self.assertEqual(len(list(csv.reader(f))), 1 + 42)


if __name__ == "__main__":
    unittest.main()