"""Tests für ursache.py (nur Standardbibliothek).

Rechentests mit erfundenen Werten; ein Test liest die committeten Daten und
prüft nur die Struktur (14 Raketen, Reihenfolge), ohne Werte auszugeben.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -m unittest discover -s stichprobe -p "test_ursache.py" -v
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import ursache


def tool_rows(label, h1, v1, h2, v2, form="std"):
    return [
        {"label": label, "form": form, "c_w": "0.33", "burnout_h_m": h1, "burnout_v_mps": v1},
        {"label": label, "form": form, "c_w": "0.36", "burnout_h_m": h2, "burnout_v_mps": v2},
    ]


class Formulas(unittest.TestCase):
    def test_coast_without_drag(self):
        self.assertAlmostEqual(ursache.coast(1.0, 9.80665), 1.0 + 9.80665 / 2, places=12)

    def test_tool_burnout_is_pair_mean(self):
        rows = tool_rows("E2", "1.10", "16.00", "1.20", "17.00")
        self.assertEqual(ursache.tool_burnout(rows, "E2", (0.33, 0.36)), (1.15, 16.5))

    def test_tool_burnout_ignores_other_form(self):
        rows = tool_rows("R1", "1.0", "10.0", "1.0", "10.0") + \
            tool_rows("R1", "9.0", "90.0", "9.0", "90.0", form="zyl")
        self.assertEqual(ursache.tool_burnout(rows, "R1", (0.33, 0.36)), (1.0, 10.0))

    def test_missing_pair_raises(self):
        rows = tool_rows("E1", "1.0", "10.0", "1.0", "10.0")[:1]
        with self.assertRaises(ValueError):
            ursache.tool_burnout(rows, "E1", (0.33, 0.36))

    def test_row_values_and_sign(self):
        flight = {"v_burnout": 9.9, "h_burnout": 1.0}
        r = ursache.row("E2", "Stichprobe", flight, 1.0, 10.0,
                        {"d_pct": "-1.5", "S_pct": "0.7", "kpi_erfuellt": "nein"})
        self.assertAlmostEqual(r["dv_bo_pct"], -1.0, places=9)
        self.assertEqual(r["dh_bo_m"], 0.0)
        expected = 100 * (ursache.coast(1.0, 9.9) - ursache.coast(1.0, 10.0)) / ursache.coast(1.0, 10.0)
        self.assertAlmostEqual(r["d_coast_pct"], expected, places=12)
        self.assertTrue(r["vorzeichen_gleich"])

    def test_opposite_sign_detected(self):
        flight = {"v_burnout": 10.1, "h_burnout": 1.0}
        r = ursache.row("X", "Stichprobe", flight, 1.0, 10.0,
                        {"d_pct": "-0.5", "S_pct": "2.0", "kpi_erfuellt": "ja"})
        self.assertFalse(r["vorzeichen_gleich"])

    def test_rounded_zero_without_sign(self):
        self.assertEqual(ursache.de(-0.0001, 3), "0,000")
        self.assertEqual(ursache.de(-0.0251, 2), "−0,03")

    def test_pair_text(self):
        self.assertEqual(ursache.pair_of("0.32/0.37"), (0.32, 0.37))


class RealData(unittest.TestCase):
    def test_fourteen_rockets_and_files_without_printed_values(self):
        rows = ursache.collect()
        self.assertEqual([r["label"] for r in rows],
                         [f"R{i}" for i in range(10)] + ["E1", "E2", "E3", "E4"])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(ursache.main(out), 0)
            self.assertNotIn("%", printed.getvalue())
            first = {n: (out / n).read_bytes() for n in ursache.OUTPUTS}
            with contextlib.redirect_stdout(io.StringIO()):
                ursache.main(out)
            for n in ursache.OUTPUTS:
                self.assertEqual((out / n).read_bytes(), first[n], n)


if __name__ == "__main__":
    unittest.main()