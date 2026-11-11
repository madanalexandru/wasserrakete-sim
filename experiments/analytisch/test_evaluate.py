"""Tests für evaluate.py mit erfundenen Daten.

Kein Test liest die echten Messdaten.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -W error -m unittest discover -s analytisch -v
"""

import contextlib
import csv
import io
import json
import math
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import evaluate
import run

LABELS = [f"R{i}" for i in range(10)]
S_FAKE = {label: 2.0 + 0.1 * i for i, label in enumerate(LABELS)}  # erfunden, in %
H_B, V_B = 3.25, 21.5  # erfundene Brennschluss-Werte


def fly_numerically(h_b, v_b, m, k, dt=1e-4):
    """Unabhängige Probe: m dv/dt = -m g - k v^2 (Aufstieg) mit RK4 bis v = 0.

    Der Rest bis v = 0 wird mit konstanter Verzögerung genähert.
    """
    def f(v):
        return -evaluate.G - k / m * v * abs(v)

    h, v = h_b, v_b
    while True:
        k1 = f(v)
        k2 = f(v + dt / 2 * k1)
        k3 = f(v + dt / 2 * k2)
        k4 = f(v + dt * k3)
        v_new = v + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        if v_new <= 0:
            # Rest des Wegs bis v = 0 bei näherungsweise konstanter Verzögerung
            return h + v**2 / (2 * -f(v))
        # Höhe: Mittelwert der Geschwindigkeit nach Simpson (v ist glatt)
        v_mid = v + dt / 2 * (k1 + k2) / 2
        h += dt / 6 * (v + 4 * v_mid + v_new)
        v = v_new


def config(label, case):
    return {**run.BASE, **run.CHANGES[label], "c_w": run.CASES[case]}


def write_fake(data_dir, eps_wanted=None, status=None, v_b=None):
    """Erfundene Messdaten: h_Modell = h_ana * (1 + eps) mit eps je (Rakete, Fall)."""
    eps_wanted = eps_wanted or {}
    status = status or {}
    v_b = v_b or {}
    data_dir.mkdir(parents=True)
    rows = []
    for i, label in enumerate(LABELS):
        for case in ("F1", "F2"):
            key = (label, case)
            cfg = config(label, case)
            st = status.get(key, "201")
            row = {"label": label, "fall": case, "c_w": repr(cfg["c_w"]),
                   "rocket_id": 100 + len(rows), "flight_id": "", "status": st,
                   "fehler": "", "file": ""}
            if st == "201":
                vb = v_b.get(key, V_B + i)
                water = 1e-6 * i
                if vb > 0:
                    if case == "F1":
                        h_ana = evaluate.h_ana_f1(H_B, vb)
                    else:
                        m = evaluate.mass(cfg["m_empty"], water)
                        h_ana = evaluate.h_ana_f2(H_B, vb, m, evaluate.drag_k(
                            cfg["c_w"], cfg["d_body"]))
                    apogee = h_ana * (1 + eps_wanted.get(key, 0.0))
                else:
                    apogee = H_B
                flight = {"id": 500 + len(rows), **cfg, "temp0": 293.15, "apogee": apogee,
                          "h_burnout": H_B, "v_burnout": vb, "water_rest": water}
                row["flight_id"] = flight["id"]
                row["file"] = f"{label}_{case}_flug_{flight['id']}.json"
                (data_dir / row["file"]).write_bytes(json.dumps(flight).encode("utf-8"))
            else:
                row["fehler"] = "erfunden"
            rows.append(row)
    with open(data_dir / run.MANIFEST_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=run.MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_kennzahlen(cw_dir, S=None):
    (cw_dir / "results").mkdir(parents=True)
    with open(cw_dir / "results" / "kennzahlen.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["label", "h_ref_m", "S_pct"])
        for label, s in (S or S_FAKE).items():
            writer.writerow([label, "1.0", repr(s)])


class Formulas(unittest.TestCase):
    def test_constants_as_in_note(self):
        self.assertEqual((evaluate.G, evaluate.RHO_AIR, evaluate.RHO_WATER),
                         (9.80665, 1.225, 1000.0))

    def test_f1_by_hand(self):
        self.assertEqual(evaluate.h_ana_f1(10.0, 9.80665 * 2), 10.0 + 9.80665 * 2)

    def test_f2_by_hand(self):
        # k v^2 / (m g) = e - 1 -> ln(...) = 1 -> h = h_b + m / (2k)
        m, k = 0.2, 0.003
        v = math.sqrt((math.e - 1) * m * evaluate.G / k)
        self.assertAlmostEqual(evaluate.h_ana_f2(1.0, v, m, k), 1.0 + m / (2 * k), places=12)

    def test_f2_tends_to_f1_for_small_k(self):
        h1 = evaluate.h_ana_f1(H_B, V_B)
        h2 = evaluate.h_ana_f2(H_B, V_B, 0.15, 1e-12)
        self.assertAlmostEqual(h2, h1, places=8)

    def test_f2_matches_independent_integration(self):
        for m, v_b, d in ((0.15, 25.0, 0.09), (0.25, 15.0, 0.102), (0.10, 35.0, 0.079)):
            k = evaluate.drag_k(0.345, d)
            with self.subTest(m=m, v_b=v_b):
                h_num = fly_numerically(H_B, v_b, m, k)
                h_ana = evaluate.h_ana_f2(H_B, v_b, m, k)
                self.assertLess(abs(h_num - h_ana) / h_ana, 1e-6)

    def test_drag_k(self):
        self.assertAlmostEqual(evaluate.drag_k(0.345, 0.09),
                               0.5 * 1.225 * 0.345 * math.pi * 0.09**2 / 4, places=15)

    def test_mass(self):
        self.assertEqual(evaluate.mass(0.15, 2e-5), 0.15 + 0.02)

    def test_eps_in_percent(self):
        self.assertAlmostEqual(evaluate.eps_pct(101.0, 100.0), 1.0, places=12)
        self.assertAlmostEqual(evaluate.eps_pct(99.0, 100.0), 1.0, places=12)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.cw = Path(self.tmp.name) / "cw"
        write_kennzahlen(self.cw)

    def tearDown(self):
        self.tmp.cleanup()

    def results(self, **kwargs):
        write_fake(self.data, **kwargs)
        return evaluate.evaluate(self.data, evaluate.load_kennzahlen(self.cw))

    def get(self, results, label, case):
        return next(r for r in results if r["label"] == label and r["fall"] == case)

    def test_exact_model_gives_zero_and_all_met(self):
        res = self.results()
        self.assertEqual(len(res), 20)
        self.assertTrue(all(r["eps"] < 1e-12 for r in res))
        self.assertEqual(evaluate.summary(res), {"F1": (10, 10, 0), "F2": (10, 10, 0)})

    def test_eps_recovered(self):
        res = self.results(eps_wanted={("R3", "F2"): 1e-5, ("R4", "F1"): -2e-6})
        self.assertAlmostEqual(self.get(res, "R3", "F2")["eps"], 1e-3, delta=1e-12)
        self.assertAlmostEqual(self.get(res, "R4", "F1")["eps"], 2e-4, delta=1e-12)

    def test_threshold_is_S_over_100_in_percent(self):
        # S(R7) = 2,7 % -> Schwelle 0,027 % -> eps 2,6e-4 erfüllt, 2,8e-4 nicht
        res = self.results(eps_wanted={("R7", "F1"): 2.6e-4, ("R7", "F2"): 2.8e-4})
        self.assertAlmostEqual(self.get(res, "R7", "F1")["schwelle"], 0.027, places=12)
        self.assertTrue(self.get(res, "R7", "F1")["erfuellt"])
        self.assertFalse(self.get(res, "R7", "F2")["erfuellt"])
        self.assertEqual(evaluate.summary(res)["F2"], (9, 10, 0))

    def test_equal_to_threshold_is_met(self):
        # eps genau gleich S/100 (2,0 / 100 = 0,02) zählt als erfüllt (<=)
        row = {"label": "R0", "fall": "F1", "c_w": "0.0", "status": "201"}
        flight = {"c_w": 0.0, "h_burnout": H_B, "v_burnout": V_B, "apogee": 50.0,
                  "water_rest": 0.0}
        with unittest.mock.patch.object(evaluate, "eps_pct", return_value=2.0 / 100):
            r = evaluate.assess(row, flight, S_pct=2.0)
        self.assertEqual(r["eps"], r["schwelle"])
        self.assertTrue(r["erfuellt"])

    def test_422_not_evaluable(self):
        res = self.results(status={("R2", "F1"): "422"})
        r = self.get(res, "R2", "F1")
        self.assertEqual((r["auswertbar"], r["grund"], r["eps"]), (False, "Status 422", None))
        self.assertEqual(evaluate.summary(res)["F1"], (9, 9, 1))

    def test_non_positive_burnout_speed_not_evaluable(self):
        res = self.results(v_b={("R5", "F2"): 0.0, ("R6", "F2"): -1.0})
        for label in ("R5", "R6"):
            r = self.get(res, label, "F2")
            self.assertEqual((r["auswertbar"], r["grund"]), (False, "v_burnout <= 0"))
        self.assertEqual(evaluate.summary(res)["F2"], (8, 8, 2))

    def test_wrong_cw_raises(self):
        write_fake(self.data)
        path = next(self.data.glob("R0_F1_*.json"))
        flight = json.loads(path.read_bytes())
        flight["c_w"] = 0.345
        path.write_bytes(json.dumps(flight).encode("utf-8"))
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, evaluate.load_kennzahlen(self.cw))

    def test_wrong_manifest_order_raises(self):
        write_fake(self.data)
        path = self.data / run.MANIFEST_NAME
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows[0], rows[1] = rows[1], rows[0]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=run.MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, evaluate.load_kennzahlen(self.cw))

    def test_missing_threshold_raises(self):
        write_fake(self.data)
        S = dict(S_FAKE)
        del S["R9"]
        with self.assertRaises(ValueError):
            evaluate.evaluate(self.data, S)

    def test_f2_uses_mass_with_water_rest(self):
        res = self.results()
        r = self.get(res, "R4", "F2")
        self.assertEqual(r["m"], evaluate.mass(run.BASE["m_empty"], 4e-6))
        self.assertIsNone(self.get(res, "R4", "F1")["m"])


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
        code, out = self.run_main(eps_wanted={("R1", "F1"): 3.3333e-4})
        self.assertEqual(code, 0)
        for name in evaluate.OUTPUTS:
            self.assertTrue((self.out / name).exists())
        self.assertEqual(out.splitlines(),
                         [f"geschrieben: results/{n}" for n in evaluate.OUTPUTS])

    def test_csv_columns_and_full_precision(self):
        self.run_main(eps_wanted={("R1", "F1"): 3.3333e-4})
        with open(self.out / "analytisch.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), evaluate.COLUMNS)
        self.assertEqual(len(rows), 20)
        r = rows[2]  # R1 F1
        self.assertEqual((r["label"], r["fall"], r["erfuellt"]), ("R1", "F1", "nein"))
        self.assertAlmostEqual(float(r["eps_pct"]), 3.3333e-2, delta=1e-12)
        self.assertNotIn(b"\r", (self.out / "analytisch.csv").read_bytes())

    def test_md_counts_and_decimal_comma(self):
        self.run_main(eps_wanted={("R1", "F1"): 3.3333e-4}, status={("R2", "F2"): "422"})
        md = (self.out / "analytisch.md").read_text(encoding="utf-8")
        self.assertIn("F1 (ohne Widerstand): 9 von 10 auswertbaren Raketen erfüllt; "
                      "nicht auswertbar: 0.", md)
        self.assertIn("F2 (mit Widerstand, c_w = 0,345): 9 von 9 auswertbaren Raketen "
                      "erfüllt; nicht auswertbar: 1.", md)
        self.assertIn("| R1 | 3,33e-02 (nein) |", md)
        self.assertIn("n. a. (Status 422)", md)
        self.assertIn("| 2,10e-02 |", md)  # S(R1) = 2,1 % -> 0,021 %


if __name__ == "__main__":
    unittest.main()