"""Tests für evaluate.py mit erfundenen Daten (keine Messwerte).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -m unittest discover -s cw_sensitivitaet -v"
"""

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

import evaluate
import run

# Erfundene, lineare Kurve: h(c) = A - B * c. Lineare Interpolation ist dafür exakt.
A, B = 100.0, 40.0


def h_lin(c):
    return A - B * c


def write_fake_data(data_dir, labels=("R0", "R1"), v_burnout=30.0, drop_step=None, d_body_jump=False):
    """Schreibt manifest.csv und je Rakete eine CSV wie der Export (nur benötigte Spalten)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for n, label in enumerate(labels):
        config = {**run.BASE, **run.CHANGES[label], "temp0": 293.15}
        name = f"{label}_serie_{n + 1}.csv"
        cws = run.expected_cw()
        if drop_step is not None:
            cws = cws[:drop_step] + cws[drop_step + 1:]
        with open(data_dir / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["series_id", "c_w", "apogee", "v_burnout"] + evaluate.CONFIG_FIELDS)
            for i, c in enumerate(reversed(cws)):  # absichtlich unsortiert
                d_body = config["d_body"] * (1.1 if d_body_jump and i == 5 else 1.0)
                row = {**config, "d_body": d_body}
                w.writerow([n + 1, repr(c), repr(h_lin(c)), repr(v_burnout)]
                           + [repr(row[k]) for k in evaluate.CONFIG_FIELDS])
        manifest.append({"label": label, "rocket_id": n + 1, "series_id": n + 1, "file": name})
    with open(data_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(manifest)


class Interp(unittest.TestCase):
    xs = [0.0, 0.5, 1.0]
    ys = [10.0, 20.0, 40.0]

    def test_grid_points_exact(self):
        for x, y in zip(self.xs, self.ys):
            self.assertEqual(evaluate.interp(self.xs, self.ys, x), y)

    def test_between_points_linear(self):
        self.assertAlmostEqual(evaluate.interp(self.xs, self.ys, 0.25), 15.0, places=12)
        self.assertAlmostEqual(evaluate.interp(self.xs, self.ys, 0.75), 30.0, places=12)

    def test_outside_raises(self):
        with self.assertRaises(ValueError):
            evaluate.interp(self.xs, self.ys, 1.01)
        with self.assertRaises(ValueError):
            evaluate.interp(self.xs, self.ys, -0.01)


class Metrics(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"
        write_fake_data(self.data)
        self.series = evaluate.load_series(self.data)
        self.m = evaluate.metrics(self.series[0])

    def test_plan_values(self):
        self.assertEqual(evaluate.C_REF, 0.345)
        self.assertEqual(evaluate.FORM_BAND, (0.30, 0.47))
        self.assertEqual(evaluate.MESS_BAND, (0.341, 0.349))
        self.assertEqual((evaluate.RHO_MODEL, evaluate.RHO_TOOL), (1.225, 1.2039))
        self.assertEqual((evaluate.NU, evaluate.RE_LIMIT), (1.453e-5, 2e5))

    def test_series_sorted_by_cw(self):
        self.assertEqual(self.series[0]["cw"], run.expected_cw())

    def test_formulas_on_linear_curve(self):
        h_ref = h_lin(0.345)
        cw_s = 0.345 * 1.2039 / 1.225
        expected = {
            "h_ref_m": h_ref,
            "S": (h_lin(0.30) - h_ref) / h_ref,
            "delta_form": (h_lin(0.30) - h_lin(0.47)) / h_ref,
            "delta_mess": (h_lin(0.341) - h_lin(0.349)) / h_ref,
            "eps": -B * 0.345 / h_ref,
            "rho_effekt": (h_lin(cw_s) - h_ref) / h_ref,
            "cw_strich": cw_s,
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(self.m[key], value, places=12)

    def test_reynolds_below_and_above_limit(self):
        self.assertAlmostEqual(self.m["re_max"], 30.0 * 0.09 / 1.453e-5, places=6)
        self.assertFalse(self.m["re_ueber_grenze"])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "data"
        write_fake_data(data, v_burnout=35.0)
        self.assertTrue(evaluate.metrics(evaluate.load_series(data)[0])["re_ueber_grenze"])

    def test_change_text(self):
        texts = {s["label"]: evaluate.change_text(s["config"]) for s in self.series}
        self.assertEqual(texts, {"R0": "Basis", "R1": "Startdruck 3 bar"})
        all_texts = [evaluate.change_text({**run.BASE, **run.CHANGES[k]}) for k in run.CHANGES]
        self.assertEqual(all_texts, [
            "Basis", "Startdruck 3 bar", "Startdruck 7 bar", "Wasser 0,3 l", "Wasser 0,7 l",
            "Düse 15 mm", "Leermasse 100 g", "Leermasse 250 g",
            "Flasche 1 l, Durchmesser 79 mm", "Flasche 2 l, Durchmesser 102 mm",
        ])


class LoadChecks(unittest.TestCase):
    def test_missing_step_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            write_fake_data(data, drop_step=40)
            with self.assertRaises(ValueError):
                evaluate.load_series(data)

    def test_changing_config_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            write_fake_data(data, d_body_jump=True)
            with self.assertRaises(ValueError):
                evaluate.load_series(data)


class Formatting(unittest.TestCase):
    def test_decimal_comma_and_minus(self):
        self.assertEqual(evaluate.de(-1.2345, 2), "−1,23")
        self.assertEqual(evaluate.de(0.5, 3), "0,500")

    def test_scientific(self):
        self.assertEqual(evaluate.de_sci(185822.4), "1,86·10⁵")
        self.assertEqual(evaluate.de_sci(1.453e-5), "1,45·10⁻⁵")


class Outputs(unittest.TestCase):
    def run_main(self, data, out):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(evaluate.main(data, out), 0)
        return buf.getvalue()

    def test_files_written_and_console_without_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / "data", Path(tmp) / "results"
            write_fake_data(data)
            text = self.run_main(data, out)
            names = sorted(p.name for p in out.iterdir())
            self.assertEqual(names, ["abbildung_cw.png", "abbildung_cw.svg",
                                     "kennzahlen.csv", "kennzahlen.md"])
            self.assertFalse(any(ch.isdigit() for ch in text))
            for name in ["kennzahlen.csv", "kennzahlen.md", "abbildung_cw.svg"]:
                with self.subTest(name=name):
                    self.assertNotIn(b"\r", (out / name).read_bytes())

    def test_reproducible_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            write_fake_data(data)
            self.run_main(data, Path(tmp) / "a")
            self.run_main(data, Path(tmp) / "b")
            for name in ["kennzahlen.csv", "kennzahlen.md", "abbildung_cw.png", "abbildung_cw.svg"]:
                with self.subTest(name=name):
                    self.assertEqual((Path(tmp) / "a" / name).read_bytes(),
                                     (Path(tmp) / "b" / name).read_bytes())

    def test_png_300_dpi_size_and_csv_rows(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / "data", Path(tmp) / "results"
            write_fake_data(data)
            self.run_main(data, out)
            with Image.open(out / "abbildung_cw.png") as img:
                self.assertEqual(img.size, (1890, 1170))
                self.assertEqual(round(img.info["dpi"][0]), 300)
            with open(out / "kennzahlen.csv", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["label"] for r in rows], ["R0", "R1"])
            self.assertEqual(list(rows[0]), evaluate.CSV_COLUMNS)
            md = (out / "kennzahlen.md").read_text(encoding="utf-8")
            self.assertEqual(md.count("\n| R"), 2)
            self.assertNotIn(".", md.split("\n")[2].split("|")[3])  # Dezimalkomma


if __name__ == "__main__":
    unittest.main()