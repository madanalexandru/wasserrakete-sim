"""Tests für evaluate.py.

Die meisten Tests nutzen erfundene Daten. Zwei Tests rechnen mit den
committeten Daten von R0 bis R9 nach, dass S, Re_max, d und e genauso
entstehen wie im c_w-Plan und im Tool-Vergleich. Zwei Tests lesen die echten
Daten der Stichprobe und prüfen nur Struktur, Kontrollen und Paare, ohne
Werte auszugeben.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -m unittest discover -s stichprobe -v"
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
EXPERIMENTS = Path(evaluate.__file__).resolve().parent.parent
SCAN_COLS = ["id", "series_id", "model_version", "v_bottle", "v_water0", "p0_gauge",
             "d_nozzle", "m_empty", "c_w", "d_body", "temp0", "apogee", "v_burnout"]


def tool_row(lauf, label, cw, h, impulse="10.00", remark=""):
    """Eine Zeile wie im Protokoll; h=None -> NaN-Anzeige (leere Felder)."""
    if h is None:
        return [lauf, label, "std", cw, "", "", "", "0.06", "", "", "", "NaN"]
    return [lauf, label, "std", cw, h, "3.00", impulse, "0.06", "0.07", "1.50", "40.00", remark]


def base_rows():
    """Gültiges Protokoll: A0, je Eckrakete 0.33 und 0.36, K-E1."""
    rows, n = [[1, "A0", "std", "0.50", *A0, ""]], 2
    for label in evaluate.LABELS:
        for cw, h in (("0.33", "52.00"), ("0.36", "50.00")):
            rows.append(tool_row(n, label, cw, h))
            n += 1
    rows.append(tool_row(n, "K-E1", "0.33", "52.00"))
    rows.append(tool_row(n + 1, "K-E1", "0.36", "50.00"))
    return rows


def write_tool(path, rows, lineterminator="\r\n"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator=lineterminator)
        w.writerow(COLS)
        w.writerows(rows)


def replace(rows, label, cw, new):
    return [new if (r[1], r[3]) == (label, cw) else r for r in rows]


def write_data(data_dir, apogee=51.0, cw_flight=None, scan_change=None, flight_change=None):
    """Übersicht, Scans (h = 80 − 60·c_w, v_burnout = 40) und Flüge wie von run.py."""
    with open(data_dir / run.MANIFEST_NAME, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(run.MANIFEST_COLUMNS)
        for i, (label, config) in enumerate(run.corners()):
            scan_file, flight_file = f"scan_{label}_serie_{i}.csv", f"modell_{label}_flug_{i}.json"
            cfg_scan = {**config, **(scan_change or {})}
            with open(data_dir / scan_file, "w", newline="", encoding="utf-8") as g:
                v = csv.writer(g, lineterminator="\r\n")
                v.writerow(SCAN_COLS)
                for j, cw in enumerate(run.expected_cw()):
                    v.writerow([j, i, "1", *(repr(cfg_scan[k]) for k in
                                             ["v_bottle", "v_water0", "p0_gauge", "d_nozzle",
                                              "m_empty"]),
                                repr(cw), repr(cfg_scan["d_body"]), "293.15",
                                repr(80.0 - 60.0 * cw), "40.0"])
            flight = {"id": i, "series_id": None, "model_version": "1", **config,
                      "c_w": run.CW_STRICH if cw_flight is None else cw_flight,
                      "temp0": 293.15, "apogee": apogee, **(flight_change or {})}
            (data_dir / flight_file).write_text(json.dumps(flight), encoding="utf-8")
            w.writerow([label, 10 + i, i, scan_file, 20 + i, i, flight_file])


class Setup:
    def make(self, rows=None, **data):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data, self.out = root / "data", root / "results"
        self.data.mkdir()
        write_tool(self.data / "tool_werte.csv", base_rows() if rows is None else rows)
        write_data(self.data, **data)

    def run_main(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(evaluate.main(self.data, self.out), 0)
        return out.getvalue()

    def result_rows(self):
        with open(self.out / "stichprobe.csv", newline="", encoding="utf-8") as f:
            return {r["label"]: r for r in csv.DictReader(f)}

    def tearDown(self):
        if hasattr(self, "tmp"):
            self.tmp.cleanup()


class PairRule(Setup, unittest.TestCase):
    def tool(self):
        return evaluate.load_tool(self.data / "tool_werte.csv")

    def test_main_pair_is_mean(self):
        self.make()
        self.assertEqual(evaluate.tool_value(self.tool(), "E1"), {"h": 51.0, "pair": (0.33, 0.36)})

    def test_nan_uses_replacement_pair(self):
        rows = replace(base_rows(), "E2", "0.36", tool_row(5, "E2", "0.36", None))
        rows += [tool_row(12, "E2", "0.32", "53.00"), tool_row(13, "E2", "0.37", "49.00")]
        self.make(rows)
        self.assertEqual(evaluate.tool_value(self.tool(), "E2"), {"h": 51.0, "pair": (0.32, 0.37)})

    def test_both_pairs_invalid_is_not_evaluable(self):
        rows = replace(base_rows(), "E3", "0.36", tool_row(7, "E3", "0.36", "50.00", "9.00"))
        rows += [tool_row(12, "E3", "0.32", "53.00"), tool_row(13, "E3", "0.37", None)]
        self.make(rows)
        self.assertIsNone(evaluate.tool_value(self.tool(), "E3"))

    def test_impulse_tolerance_boundary(self):
        ok = replace(base_rows(), "E1", "0.36", tool_row(3, "E1", "0.36", "50.00", "10.05"))
        self.make(ok)
        self.assertIsNotNone(evaluate.tool_value(self.tool(), "E1"))
        self.tmp.cleanup()
        bad = replace(base_rows(), "E1", "0.36", tool_row(3, "E1", "0.36", "50.00", "10.06"))
        self.make(bad)
        self.assertIsNone(evaluate.tool_value(self.tool(), "E1"))

    def test_missing_main_pair_raises(self):
        rows = [r for r in base_rows() if (r[1], r[3]) != ("E4", "0.36")]
        self.make(rows)
        with self.assertRaises(ValueError):
            evaluate.tool_value(self.tool(), "E4")

    def test_duplicate_run_raises(self):
        self.make(base_rows() + [tool_row(12, "E1", "0.33", "52.00")])
        with self.assertRaises(ValueError):
            self.tool()

    def test_unplanned_run_with_remark_is_ignored(self):
        extra = tool_row(12, "X-E1", "0.33", "99.00", remark="Eingabefehler; nicht ausgewertet")
        self.make(base_rows() + [extra])
        rows = self.tool()
        self.assertNotIn("X-E1", [r["label"] for r in rows])
        self.assertEqual(evaluate.tool_value(rows, "E1")["h"], 51.0)

    def test_unplanned_run_without_remark_raises(self):
        self.make(base_rows() + [tool_row(12, "X-E1", "0.33", "99.00")])
        with self.assertRaises(ValueError):
            self.tool()

    def test_other_form_raises(self):
        rows = base_rows()
        rows[2] = [rows[2][0], rows[2][1], "zyl", *rows[2][3:]]
        self.make(rows)
        with self.assertRaises(ValueError):
            self.tool()

    def test_lf_and_crlf_give_same_rows(self):
        self.make()
        crlf = self.tool()
        write_tool(self.data / "tool_werte.csv", base_rows(), lineterminator="\n")
        self.assertEqual(self.tool(), crlf)


class Controls(Setup, unittest.TestCase):
    def check(self, rows):
        self.make(rows)
        evaluate.check_controls(evaluate.load_tool(self.data / "tool_werte.csv"))

    def test_valid_controls_pass(self):
        self.check(base_rows())

    def test_anchor_mismatch_raises(self):
        rows = base_rows()
        rows[0] = [1, "A0", "std", "0.50", "49.58", *A0[1:], ""]
        with self.assertRaises(ValueError):
            self.check(rows)

    def test_control_mismatch_raises(self):
        rows = replace(base_rows(), "K-E1", "0.36", tool_row(11, "K-E1", "0.36", "50.01"))
        with self.assertRaises(ValueError):
            self.check(rows)

    def test_control_missing_one_cw_raises(self):
        rows = [r for r in base_rows() if (r[1], r[3]) != ("K-E1", "0.36")]
        with self.assertRaises(ValueError):
            self.check(rows)

    def test_main_stops_on_failed_control_and_writes_nothing(self):
        self.make(replace(base_rows(), "K-E1", "0.33", tool_row(10, "K-E1", "0.33", "52.01")))
        out = Path(self.tmp.name) / "results"
        with self.assertRaises(ValueError):
            evaluate.main(self.data, out)
        self.assertFalse(out.exists())


class Scan(unittest.TestCase):
    def test_metrics_on_linear_curve(self):
        cw = run.expected_cw()
        h = [80.0 - 60.0 * c for c in cw]
        m = evaluate.scan_metrics(cw, h, [40.0] * len(cw), 0.1)
        h_ref = 80.0 - 60.0 * 0.345
        self.assertAlmostEqual(m["h_ref"], h_ref, places=9)
        self.assertAlmostEqual(m["S_pct"], 100 * (62.0 - h_ref) / h_ref, places=9)
        self.assertAlmostEqual(m["re_max"], 40.0 * 0.1 / 1.453e-5, places=3)

    def test_interp_hits_grid_points_exactly(self):
        self.assertEqual(evaluate.interp([0.0, 0.5, 1.0], [3.0, 7.0, 1.0], 0.5), 7.0)
        with self.assertRaises(ValueError):
            evaluate.interp([0.0, 1.0], [1.0, 2.0], 1.5)


class Loading(Setup, unittest.TestCase):
    def load(self):
        manifest = evaluate.load_manifest(self.data)
        return evaluate.load_model(self.data, manifest), evaluate.load_scans(self.data, manifest)

    def test_valid_data_loads(self):
        self.make()
        model, scans = self.load()
        self.assertEqual(sorted(model), ["E1", "E2", "E3", "E4"])
        self.assertEqual(sorted(scans), ["E1", "E2", "E3", "E4"])

    def test_wrong_model_cw_raises(self):
        self.make(cw_flight=0.345)
        with self.assertRaises(ValueError):
            self.load()

    def test_wrong_flight_config_raises(self):
        self.make(flight_change={"v_water0": 0.5e-3})
        with self.assertRaises(ValueError):
            self.load()

    def test_wrong_scan_config_raises(self):
        self.make(scan_change={"m_empty": 0.15})
        with self.assertRaises(ValueError):
            self.load()


class Kpi(Setup, unittest.TestCase):
    def test_boundary_counts_as_met(self):
        self.assertTrue(evaluate.kpi_met(-5.0, 5.0))
        self.assertFalse(evaluate.kpi_met(5.000001, 5.0))

    def test_deviation_kpi_and_e(self):
        self.make(apogee=51.0 * 1.02)
        self.run_main()
        r = self.result_rows()["E1"]
        self.assertAlmostEqual(float(r["d_pct"]), 2.0, places=9)
        self.assertEqual(r["kpi_erfuellt"], "ja")  # S ca. 4,55 % bei h = 80 − 60·c_w
        self.assertAlmostEqual(float(r["e_pct"]), 0.0, places=9)  # linear: kein Fehler
        self.assertEqual(r["paar"], "0.33/0.36")

    def test_kpi_missed(self):
        self.make(apogee=51.0 * 1.10)
        self.run_main()
        self.assertEqual(self.result_rows()["E1"]["kpi_erfuellt"], "nein")

    def test_not_evaluable_reported(self):
        rows = replace(base_rows(), "E4", "0.33", tool_row(8, "E4", "0.33", None))
        self.make(rows)
        self.run_main()
        self.assertEqual(self.result_rows()["E4"]["kpi_erfuellt"], "")
        md = (self.out / "stichprobe.md").read_text(encoding="utf-8")
        self.assertIn("(nicht auswertbar: E4)", md)


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
        md = (self.out / "stichprobe.md").read_text(encoding="utf-8")
        self.assertIn("| E1 | 1 l / 79 mm, 7 bar, Düse 22 mm, 100 g, Wasser 0,33 l "
                      "| 51,00 | 51,00 | 0,00 |", md)
        self.assertIn("| E4 | 2 l / 102 mm, 3 bar, Düse 15 mm, 250 g, Wasser 0,66 l |", md)
        self.assertIn("KPI erfüllt: 4 von 4 auswertbaren Eckraketen (nicht auswertbar: keine).",
                      md)


class SameMethodAsR0toR9(unittest.TestCase):
    """Nachrechnung mit den committeten Daten von R0 bis R9 (keine Ausgabe)."""

    @staticmethod
    def cw_scan(label):
        data = EXPERIMENTS / "cw_sensitivitaet" / "data"
        with open(data / "manifest.csv", newline="", encoding="utf-8") as f:
            name = {m["label"]: m["file"] for m in csv.DictReader(f)}[label]
        rows = evaluate.read_scan_rows(data / name)
        return ([float(r["c_w"]) for r in rows], [float(r["apogee"]) for r in rows],
                [float(r["v_burnout"]) for r in rows], float(rows[0]["d_body"]))

    def test_S_and_re_max_equal_kennzahlen(self):
        path = EXPERIMENTS / "cw_sensitivitaet" / "results" / "kennzahlen.csv"
        with open(path, newline="", encoding="utf-8") as f:
            kennzahlen = list(csv.DictReader(f))
        self.assertEqual(len(kennzahlen), 10)
        for k in kennzahlen:
            with self.subTest(label=k["label"]):
                m = evaluate.scan_metrics(*self.cw_scan(k["label"]))
                self.assertEqual(repr(m["S_pct"]), k["S_pct"])
                self.assertEqual(repr(m["re_max"]), k["re_max"])
                self.assertEqual(repr(m["h_ref"]), k["h_ref_m"])

    def test_d_and_e_equal_tool_vergleich(self):
        base = EXPERIMENTS / "tool_vergleich"
        with open(base / "data" / "tool_werte.csv", newline="", encoding="utf-8") as f:
            raw = [r for r in csv.DictReader(f) if r["form"] == "std" and r["label"][0] == "R"]
        rows = [{"lauf": int(r["lauf"]), "label": r["label"], "c_w": float(r["c_w"]),
                 **{k: evaluate.num(r[k]) for k in evaluate.VALUE_FIELDS}} for r in raw]
        with open(base / "results" / "vergleich.csv", newline="", encoding="utf-8") as f:
            vergleich = list(csv.DictReader(f))
        self.assertEqual(len(vergleich), 10)
        for v in vergleich:
            with self.subTest(label=v["label"]):
                tool = evaluate.tool_value(rows, v["label"])
                self.assertEqual(repr(tool["h"]), v["h_tool_m"])
                h_model = float(v["h_modell_m"])
                self.assertEqual(repr(100 * (h_model - tool["h"]) / tool["h"]), v["d_pct"])
                cw, h, _, _ = self.cw_scan(v["label"])
                apogee = dict(zip(cw, h))
                h_ref = evaluate.interp(cw, h, evaluate.C_REF)
                c1, c2 = tool["pair"]
                e = 100 * ((apogee[c1] + apogee[c2]) / 2 - h_ref) / h_ref
                self.assertEqual(repr(e), v["e_pct"])


class RealData(unittest.TestCase):
    """Echte Daten der Stichprobe: nur Struktur, Kontrollen und Paare."""

    def test_protocol_structure_controls_and_pairs(self):
        rows = evaluate.load_tool(evaluate.DATA_DIR / "tool_werte.csv")
        self.assertEqual(len(rows), 11)  # 12 Läufe, X-E1 nicht ausgewertet
        evaluate.check_controls(rows)
        for label in evaluate.LABELS:
            with self.subTest(label=label):
                self.assertEqual(evaluate.tool_value(rows, label)["pair"], (0.33, 0.36))

    def test_model_data_load(self):
        manifest = evaluate.load_manifest(evaluate.DATA_DIR)
        self.assertEqual(sorted(evaluate.load_model(evaluate.DATA_DIR, manifest)), evaluate.LABELS)
        self.assertEqual(sorted(evaluate.load_scans(evaluate.DATA_DIR, manifest)), evaluate.LABELS)


if __name__ == "__main__":
    unittest.main()