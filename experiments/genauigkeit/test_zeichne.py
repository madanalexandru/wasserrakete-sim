"""Tests für zeichne.py: Vollständigkeit, Werte wie in den CSV-Dateien, Reproduzierbarkeit.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -W error -m unittest discover -s genauigkeit -v"
"""

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

import zeichne


def csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestDaten(unittest.TestCase):
    def test_alle_14_raketen_in_fester_reihenfolge(self):
        labels = [r["label"] for r in zeichne.load(zeichne.VERGLEICH) + zeichne.load(zeichne.STICHPROBE)]
        self.assertEqual(labels, [f"R{i}" for i in range(10)] + [f"E{i}" for i in range(1, 5)])

    def test_werte_wie_in_den_csv_dateien(self):
        for path in (zeichne.VERGLEICH, zeichne.STICHPROBE):
            for row, raw in zip(zeichne.load(path), csv_rows(path)):
                self.assertEqual(row["d"], float(raw["d_pct"]))
                self.assertEqual(row["S"], float(raw["S_pct"]))
                self.assertEqual(row["ok"], raw["kpi_erfuellt"] == "ja")

    def test_genau_e2_verfehlt_den_kpi(self):
        rows = zeichne.load(zeichne.VERGLEICH) + zeichne.load(zeichne.STICHPROBE)
        self.assertEqual([r["label"] for r in rows if not r["ok"]], ["E2"])

    def test_widerspruch_in_kpi_spalte_wird_erkannt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.csv"
            p.write_text("label,d_pct,S_pct,kpi_erfuellt\nX,2.0,1.0,ja\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                zeichne.load(p)

    def test_luecke_zwischen_r_und_e(self):
        x = zeichne.positions(10, 4)
        self.assertEqual(len(x), 14)
        self.assertEqual(x[10] - x[9], 1 + zeichne.GAP)


class TestAbbildung(unittest.TestCase):
    def run_main(self, out):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(zeichne.main(out_dir=out), 0)

    def test_balken_entsprechen_den_werten(self):
        rows_r, rows_e = zeichne.load(zeichne.VERGLEICH), zeichne.load(zeichne.STICHPROBE)
        with tempfile.TemporaryDirectory() as tmp:
            _x, bars = zeichne.plot(rows_r, rows_e, Path(tmp))
        self.assertEqual(len(bars), 14)
        for bar, r in zip(bars, rows_r + rows_e):
            self.assertAlmostEqual(bar.get_height(), r["d"], places=12)
            self.assertEqual(bar.get_hatch(), None if r["ok"] else "////")

    def test_dateien_entstehen_und_sind_reproduzierbar(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.run_main(Path(a))
            self.run_main(Path(b))
            for name in zeichne.OUTPUTS:
                fa, fb = Path(a) / name, Path(b) / name
                self.assertTrue(fa.stat().st_size > 0)
                self.assertEqual(fa.read_bytes(), fb.read_bytes(), name)


if __name__ == "__main__":
    unittest.main()