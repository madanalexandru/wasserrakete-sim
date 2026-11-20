"""Tests für run.py ohne laufende API (nur Standardbibliothek).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -W error -m unittest discover -s stabilitaet -v
"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import run

# Unabhängig von run.py aus der Vorab-Notiz (Abschnitt 2) abgeschrieben.
EXPECTED_GEOMETRY = {
    "nose_shape": "ogive", "l_nose": 0.10, "n_fins": 3, "fin_root_chord": 0.10,
    "fin_tip_chord": 0.05, "fin_span": 0.08, "fin_sweep": 0.05, "l_total": 0.42,
    "x_fin": 0.32, "x_cg_empty": 0.21,
}
EXPECTED_R0 = {"v_bottle": 1.5e-3, "v_water0": 0.5e-3, "p0_gauge": 5e5, "d_nozzle": 0.022,
               "m_empty": 0.15, "c_w": 0.345, "d_body": 0.09}
# Testgeometrie: bewusst NICHT die Geometrie aus der Notiz.
TEST_GEOMETRY = {
    "nose_shape": "cone", "l_nose": 0.2, "n_fins": 4, "fin_root_chord": 0.2,
    "fin_tip_chord": 0.1, "fin_span": 0.1, "fin_sweep": 0.1, "l_total": 0.7,
    "x_fin": 0.5, "x_cg_empty": 0.3,
}
SECRET = 98.7654321  # Testwert; darf nie ausgegeben werden


class FakeApi:
    """Spielt die API nach: legt Raketen an und rechnet Flüge."""

    def __init__(self, apogee=SECRET, drop_stability=False):
        self.rockets, self.apogee, self.drop = {}, apogee, drop_stability

    def __call__(self, method, path, payload=None, timeout=60):
        if method == "POST" and path == "/rockets":
            rid = len(self.rockets) + 1
            stab = None
            if "nose_shape" in payload and not self.drop:
                stab = {k: SECRET for k in run.STABILITY_FIELDS}
            body = {"id": rid, **payload, "stability": stab}
            self.rockets[rid] = payload
            return 201, json.dumps(body).encode()
        if method == "POST" and path.endswith("/flights"):
            rid = int(path.split("/")[2])
            body = {"id": 100 + rid, "rocket_id": rid, **self.rockets[rid], "apogee": self.apogee}
            return 201, json.dumps(body).encode()
        return 404, b"{}"


class TestKonfiguration(unittest.TestCase):
    def test_geometrie_wie_in_der_notiz(self):
        self.assertEqual(run.GEOMETRY, EXPECTED_GEOMETRY)

    def test_r0_wie_in_der_notiz(self):
        self.assertEqual(run.R0, EXPECTED_R0)

    def test_r0g_ist_r0_plus_geometrie(self):
        (l0, c0), (lg, cg) = run.rockets()
        self.assertEqual((l0, lg), ("R0", "R0G"))
        self.assertEqual(c0, EXPECTED_R0)
        self.assertEqual(cg, {**EXPECTED_R0, **EXPECTED_GEOMETRY})


class TestMessung(unittest.TestCase):
    def test_schreibt_antworten_unveraendert_und_ohne_werte_auf_der_konsole(self):
        with mock.patch.object(run, "request", FakeApi()), tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                results = run.measure(TEST_GEOMETRY)
                run.write_results(results, Path(tmp))
            self.assertNotIn(str(SECRET), out.getvalue())
            with open(Path(tmp) / run.MANIFEST_NAME, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["label"] for r in rows], ["R0", "R0G"])
            for r, res in zip(rows, results):
                self.assertEqual((Path(tmp) / r["rocket_file"]).read_bytes(), res["rocket_body"])
                self.assertEqual((Path(tmp) / r["flight_file"]).read_bytes(), res["flight_body"])

    def test_fehlende_stabilitaet_bricht_ab(self):
        with mock.patch.object(run, "request", FakeApi(drop_stability=True)):
            with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                run.measure(TEST_GEOMETRY)

    def test_abweichendes_feld_wird_erkannt(self):
        with self.assertRaises(RuntimeError):
            run.check_rocket("X", {"l_nose": 0.1}, {"l_nose": 0.2, "stability": None})

    def test_falscher_status_bricht_ab(self):
        with self.assertRaises(RuntimeError):
            run.expect(422, b"detail", 201, "Test")

    def test_kein_zweiter_lauf_wenn_schon_gemessen(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / run.MANIFEST_NAME).write_text("x", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run.main(Path(tmp)), 2)


if __name__ == "__main__":
    unittest.main()