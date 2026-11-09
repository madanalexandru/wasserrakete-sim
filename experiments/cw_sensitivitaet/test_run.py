"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -m unittest discover -s cw_sensitivitaet -v
"""

import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run

# Erwartete Raketen, unabhängig von run.py abgeschrieben aus dem Versuchsplan.
EXPECTED = {
    "R0": {},
    "R1": {"p0_gauge": 3e5},
    "R2": {"p0_gauge": 7e5},
    "R3": {"v_water0": 0.3e-3},
    "R4": {"v_water0": 0.7e-3},
    "R5": {"d_nozzle": 0.015},
    "R6": {"m_empty": 0.10},
    "R7": {"m_empty": 0.25},
    "R8": {"v_bottle": 1.0e-3, "d_body": 0.079},
    "R9": {"v_bottle": 2.0e-3, "d_body": 0.102},
}
EXPECTED_BASE = {
    "v_bottle": 1.5e-3, "v_water0": 0.5e-3, "p0_gauge": 5e5, "d_nozzle": 0.022,
    "m_empty": 0.15, "c_w": 0.5, "d_body": 0.09,
}


def fake_csv(series_id, cw_values, extra_rows=0):
    """CSV wie der Export (Komma, CRLF), nur mit den geprüften Spalten."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["id", "series_id", "c_w", "apogee"])
    for i, cw in enumerate(list(cw_values) + [1.0] * extra_rows):
        writer.writerow([i + 1, series_id, repr(cw), ""])
    return out.getvalue().encode("utf-8")


class RocketSet(unittest.TestCase):
    def test_labels_in_order(self):
        self.assertEqual([label for label, _ in run.rockets()],
                         [f"R{i}" for i in range(10)])

    def test_base(self):
        self.assertEqual(run.BASE, EXPECTED_BASE)

    def test_each_rocket_differs_only_in_planned_fields(self):
        for label, config in run.rockets():
            with self.subTest(label=label):
                self.assertEqual(config, {**EXPECTED_BASE, **EXPECTED[label]})

    def test_nozzle_smaller_than_body_and_water_smaller_than_bottle(self):
        for label, c in run.rockets():
            with self.subTest(label=label):
                self.assertLess(c["d_nozzle"], c["d_body"])
                self.assertLess(c["v_water0"], c["v_bottle"])

    def test_no_temperature_and_no_geometry_sent(self):
        for label, config in run.rockets():
            payload = run.rocket_payload(label, config)
            self.assertEqual(set(payload), set(EXPECTED_BASE) | {"name"})

    def test_names_are_ascii(self):
        for label, config in run.rockets():
            self.assertTrue(run.rocket_payload(label, config)["name"].isascii())
            self.assertTrue(run.series_payload(label)["name"].isascii())


class SeriesPlan(unittest.TestCase):
    def test_series_payload(self):
        p = run.series_payload("R0")
        self.assertEqual(p, {"name": "cw-Sensitivitaet R0", "mode": "forward",
                             "param_name": "c_w", "param_start": 0.0,
                             "param_stop": 1.0, "n_steps": 101})

    def test_expected_cw_are_exact_hundredths(self):
        values = run.expected_cw()
        self.assertEqual(len(values), 101)
        self.assertEqual(values, [i / 100 for i in range(101)])
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[50], 0.5)
        self.assertEqual(values[-1], 1.0)


class CheckCsv(unittest.TestCase):
    def test_valid_export_passes(self):
        self.assertEqual(run.check_csv(fake_csv(7, run.expected_cw()), 7), 101)

    def test_wrong_row_count_fails(self):
        with self.assertRaises(RuntimeError):
            run.check_csv(fake_csv(7, run.expected_cw(), extra_rows=1), 7)

    def test_foreign_series_id_fails(self):
        with self.assertRaises(RuntimeError):
            run.check_csv(fake_csv(8, run.expected_cw()), 7)

    def test_wrong_cw_value_fails(self):
        values = run.expected_cw()
        values[30] = 0.31
        with self.assertRaises(RuntimeError):
            run.check_csv(fake_csv(7, values), 7)


class Writing(unittest.TestCase):
    def results(self):
        body = b"id,c_w\r\n1,0.0\r\n"
        return [{"label": "R0", "rocket_id": 11, "series_id": 5,
                 "file": "R0_serie_5.csv", "csv": body}]

    def test_csv_written_byte_for_byte_with_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            run.write_results(self.results(), data)
            self.assertEqual((data / "R0_serie_5.csv").read_bytes(), b"id,c_w\r\n1,0.0\r\n")

    def test_manifest_without_csv_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            run.write_results(self.results(), data)
            raw = (data / "manifest.csv").read_bytes()
            self.assertEqual(raw, b"label,rocket_id,series_id,file\r\nR0,11,5,R0_serie_5.csv\r\n")

    def test_existing_manifest_aborts_without_contacting_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "manifest.csv").write_text("alt", encoding="utf-8")
            with mock.patch.object(run, "request") as req, \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 2)
            req.assert_not_called()
            self.assertEqual((data / "manifest.csv").read_text(encoding="utf-8"), "alt")

    def test_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            with mock.patch.object(run, "wait_for_api"), \
                    mock.patch.object(run, "request", return_value=(422, b"{}")), \
                    mock.patch("builtins.print"):
                self.assertEqual(run.main(data), 1)
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()