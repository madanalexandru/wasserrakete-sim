"""Tests für evaluate.py mit erfundenen Daten.

Nur ein Test liest die echte tool_werte.csv; er prüft Struktur und
Gültigkeit der Paare, nicht den Vergleich mit dem Modell.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -m unittest discover -s tool_vergleich -v"
"""

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

import evaluate
import run

COLS = ["lauf", "label", "form", "c_w", "apogee_m", "t_apogee_s", "impulse_ns",
        "burn_time_s", "burnout_t_s", "burnout_h_m", "burnout_v_mps", "bemerkung"]
A0 = ["49.57", "2.89", "14.14", "0.06", "0.07", "1.87", "42.76"]


def tool_row(lauf, label, form, cw, h, impulse="10.00"):
    """Eine Zeile wie im Protokoll; h=None -> NaN-Anzeige (leere Felder)."""
    if h is None:
        return [lauf, label, form, cw, "", "", "", "0.06", "", "", "", "NaN"]
    return [lauf, label, form, cw, h, "3.00", impulse, "0.06", "0.07", "1.50", "40.00", ""]


def base_rows():
    """Gültiges Protokoll: A0, je Rakete std/zyl bei 0.33 und 0.36, K-R0."""
    rows, n = [[1, "A0", "std", "0.50", *A0, ""]], 2
    for label in evaluate.LABELS:
        for form in evaluate.FORMS:
            for cw, h in (("0.33", "52.00"), ("0.36", "50.00")):
                rows.append(tool_row(n, label, form, cw, h))
                n += 1
    rows.append(tool_row(n, "K-R0", "std", "0.33", "52.00"))
    rows.append(tool_row(n + 1, "K-R0", "std", "0.36", "50.00"))
    return rows


def write_tool(path, rows, lineterminator="\r\n"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator=lineterminator)
        w.writerow(COLS)
        w.writerows(rows)


def replace(rows, label, form, cw, new):
    return [new if (r[1], r[2], r[3]) == (label, form, cw) else r for r in rows]


def write_model(data_dir, apogee=51.0, cw=None):
    with open(data_dir / run.MANIFEST_NAME, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(run.MANIFEST_COLUMNS)
        for i, (label, config) in enumerate(run.rockets()):
            name = f"modell_{label}_flug_{i}.json"
            flight = {"id": i, "model_version": "1", **config, "temp0": 293.15,
                      "apogee": apogee}
            if cw is not None:
                flight["c_w"] = cw
            (data_dir / name).write_text(json.dumps(flight), encoding="utf-8")
            w.writerow([label, i, i, name])


def write_cw(cw_dir, S=5.0, h_ref=51.0):
    (cw_dir / "results").mkdir(parents=True)
    (cw_dir / "data").mkdir()
    with open(cw_dir / "results" / "kennzahlen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "h_ref_m", "S_pct"])
        for label in evaluate.LABELS:
            w.writerow([label, h_ref, S])
    with open(cw_dir / "data" / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "file"])
        for label in evaluate.LABELS:
            w.writerow([label, f"{label}.csv"])
            with open(cw_dir / "data" / f"{label}.csv", "w", newline="", encoding="utf-8") as g:
                v = csv.writer(g)
                v.writerow(["c_w", "apogee"])
                for i in range(101):
                    v.writerow([repr(i / 100), repr(80.0 - 60.0 * i / 100)])


class Setup:
    def make(self, rows=None, **model):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data, self.out, self.cw = root / "data", root / "results", root / "cw"
        self.data.mkdir()
        write_tool(self.data / "tool_werte.csv", base_rows() if rows is None else rows)
        write_model(self.data, **model)
        write_cw(self.cw)

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(evaluate.main(self.data, self.out, self.cw), 0)
        return out.getvalue()

    def result_rows(self):
        with open(self.out / "vergleich.csv", newline="", encoding="utf-8") as f:
            return {r["label"]: r for r in csv.DictReader(f)}

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()


class PairRule(Setup, unittest.TestCase):
    def setUp(self):
        self.make()
        self.rows = evaluate.load_tool(self.data / "tool_werte.csv")

    def test_main_pair_is_mean(self):
        v = evaluate.tool_value(self.rows, "R0", "std")
        self.assertEqual(v, {"h": 51.0, "pair": (0.33, 0.36)})

    def test_nan_uses_replacement_pair(self):
        rows = base_rows()
        rows = replace(rows, "R1", "zyl", "0.36", tool_row(8, "R1", "zyl", "0.36", None))
        rows += [tool_row(60, "R1", "zyl", "0.32", "53.00"),
                 tool_row(61, "R1", "zyl", "0.37", "49.00")]
        write_tool(self.data / "tool_werte.csv", rows)
        parsed = evaluate.load_tool(self.data / "tool_werte.csv")
        self.assertEqual(evaluate.tool_value(parsed, "R1", "zyl"),
                         {"h": 51.0, "pair": (0.32, 0.37)})

    def test_both_pairs_invalid_is_not_evaluable(self):
        rows = replace(base_rows(), "R1", "zyl", "0.36", tool_row(8, "R1", "zyl", "0.36", None))
        rows += [tool_row(60, "R1", "zyl", "0.32", "53.00"),
                 tool_row(61, "R1", "zyl", "0.37", None),
                 tool_row(62, "R1", "zyl", "0.39", "48.00")]  # nicht im Plan
        write_tool(self.data / "tool_werte.csv", rows)
        parsed = evaluate.load_tool(self.data / "tool_werte.csv")
        self.assertIsNone(evaluate.tool_value(parsed, "R1", "zyl"))

    def test_missing_replacement_pair_is_not_evaluable(self):
        rows = replace(base_rows(), "R2", "std", "0.33", tool_row(9, "R2", "std", "0.33", None))
        write_tool(self.data / "tool_werte.csv", rows)
        parsed = evaluate.load_tool(self.data / "tool_werte.csv")
        self.assertIsNone(evaluate.tool_value(parsed, "R2", "std"))

    def test_impulse_tolerance_boundary(self):
        a = {"apogee_m": 1.0, "impulse_ns": 14.16}
        self.assertTrue(evaluate.pair_valid(a, {"apogee_m": 1.0, "impulse_ns": 14.11}))
        self.assertFalse(evaluate.pair_valid(a, {"apogee_m": 1.0, "impulse_ns": 14.10}))

    def test_missing_main_pair_raises(self):
        rows = [r for r in base_rows() if (r[1], r[2], r[3]) != ("R3", "std", "0.36")]
        write_tool(self.data / "tool_werte.csv", rows)
        parsed = evaluate.load_tool(self.data / "tool_werte.csv")
        with self.assertRaises(ValueError):
            evaluate.tool_value(parsed, "R3", "std")

    def test_duplicate_run_raises(self):
        rows = base_rows() + [tool_row(99, "R0", "std", "0.33", "52.00")]
        write_tool(self.data / "tool_werte.csv", rows)
        with self.assertRaises(ValueError):
            evaluate.load_tool(self.data / "tool_werte.csv")

    def test_lf_and_crlf_give_same_rows(self):
        write_tool(self.data / "lf.csv", base_rows(), lineterminator="\n")
        self.assertEqual(evaluate.load_tool(self.data / "lf.csv"), self.rows)


class Controls(Setup, unittest.TestCase):
    def setUp(self):
        self.make()

    def test_valid_controls_pass(self):
        evaluate.check_controls(evaluate.load_tool(self.data / "tool_werte.csv"))

    def test_anchor_mismatch_raises(self):
        rows = base_rows()
        rows[0] = [1, "A0", "std", "0.50", "49.58", *A0[1:], ""]
        write_tool(self.data / "tool_werte.csv", rows)
        with self.assertRaises(ValueError):
            evaluate.check_controls(evaluate.load_tool(self.data / "tool_werte.csv"))

    def test_control_mismatch_raises(self):
        rows = replace(base_rows(), "K-R0", "std", "0.36",
                       tool_row(43, "K-R0", "std", "0.36", "50.01"))
        write_tool(self.data / "tool_werte.csv", rows)
        with self.assertRaises(ValueError):
            evaluate.check_controls(evaluate.load_tool(self.data / "tool_werte.csv"))


class Kpi(Setup, unittest.TestCase):
    def test_boundary_counts_as_met(self):
        self.assertTrue(evaluate.kpi_met(5.0, 5.0))
        self.assertTrue(evaluate.kpi_met(-5.0, 5.0))
        self.assertFalse(evaluate.kpi_met(5.01, 5.0))

    def test_deviation_and_kpi(self):
        self.make(apogee=53.55)  # h_Tool = 51, d = +5 % (Rundung knapp darunter)
        self.run_main()
        r = self.result_rows()["R0"]
        self.assertAlmostEqual(float(r["d_pct"]), 5.0, places=9)
        self.assertEqual(r["kpi_erfuellt"], "ja")

    def test_kpi_missed(self):
        self.make(apogee=48.0)  # d = -5,88 %
        self.run_main()
        r = self.result_rows()["R0"]
        self.assertLess(float(r["d_pct"]), -5.0)
        self.assertEqual(r["kpi_erfuellt"], "nein")

    def test_delta_form_and_e(self):
        rows = base_rows()
        for cw, h in (("0.33", "54.00"), ("0.36", "52.00")):  # zyl: 53 statt 51
            rows = replace(rows, "R4", "zyl", cw, tool_row(0, "R4", "zyl", cw, h))
        self.make(rows=rows)
        self.run_main()
        r = self.result_rows()["R4"]
        self.assertAlmostEqual(float(r["delta_form_pct"]), 100 * 2 / 51, places=9)
        self.assertEqual(r["form_einordnung"], "Limitation")  # 3,9 % < S = 5 %
        # Scan linear: (h(0,33)+h(0,36))/2 = 80 - 60*0,345 = 59,3; h_ref = 51
        self.assertAlmostEqual(float(r["e_pct"]), 100 * (59.3 - 51) / 51, places=9)

    def test_not_evaluable_form_reported(self):
        rows = replace(base_rows(), "R1", "zyl", "0.36", tool_row(8, "R1", "zyl", "0.36", None))
        self.make(rows=rows)
        self.run_main()
        r = self.result_rows()["R1"]
        self.assertEqual((r["delta_form_pct"], r["paar_zyl"]), ("", ""))
        self.assertEqual(r["kpi_erfuellt"], "ja")
        md = (self.out / "vergleich.md").read_text(encoding="utf-8")
        self.assertIn("Δ_Form nicht auswertbar: R1.", md)

    def test_wrong_model_cw_raises(self):
        self.make(cw=0.345)
        with self.assertRaises(ValueError):
            self.run_main()


class Output(Setup, unittest.TestCase):
    def setUp(self):
        self.make()

    def test_files_written_and_no_values_printed(self):
        printed = self.run_main()
        for name in evaluate.OUTPUTS:
            self.assertTrue((self.out / name).stat().st_size > 0, name)
        self.assertNotIn("51", printed)
        self.assertNotIn("%", printed)

    def test_reproducible(self):
        self.run_main()
        first = {n: (self.out / n).read_bytes() for n in evaluate.OUTPUTS}
        self.run_main()
        for n in evaluate.OUTPUTS:
            self.assertEqual((self.out / n).read_bytes(), first[n], n)

    def test_md_uses_decimal_comma(self):
        self.run_main()
        md = (self.out / "vergleich.md").read_text(encoding="utf-8")
        self.assertIn("| R0 | Basis | 51,00 | 51,00 | 0,00 | 5,00 | ja |", md)
        self.assertIn("KPI erfüllt: 10 von 10 auswertbaren Raketen (nicht auswertbar: keine).", md)


class RealProtocol(unittest.TestCase):
    """Echte tool_werte.csv: nur Struktur, Kontrollen und Gültigkeit der Paare."""

    def test_structure_and_pairs(self):
        rows = evaluate.load_tool(evaluate.DATA_DIR / "tool_werte.csv")
        self.assertEqual(len(rows), 47)
        evaluate.check_controls(rows)
        for label in evaluate.LABELS:
            for form in evaluate.FORMS:
                v = evaluate.tool_value(rows, label, form)
                with self.subTest(label=label, form=form):
                    if (label, form) == ("R1", "zyl"):
                        self.assertIsNone(v)
                    else:
                        self.assertEqual(v["pair"], (0.33, 0.36))


if __name__ == "__main__":
    unittest.main()