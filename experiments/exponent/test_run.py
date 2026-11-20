"""Tests für run.py: Raketen, Laufzeit-Änderung von β, Kontrolle, keine Werte auf der Konsole.

Rechnet die Physik nur für eine Testrakete, nie für R0-R9 oder E1-E4.

Start (PowerShell, im Repo-Ordner; backend nur lesend):
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\\backend:/backend:ro" -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python -W error -m unittest discover -s exponent -v
"""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import run
from app.physics import simulation, waterphase

CW_STRICH = 0.345 * 1.2039 / 1.225
# Unabhängig abgeschrieben aus tool_vergleich/run.py und stichprobe/run.py.
BASE = {"v_bottle": 1.5e-3, "v_water0": 0.5e-3, "p0_gauge": 5e5, "d_nozzle": 0.022,
        "m_empty": 0.15, "c_w": CW_STRICH, "d_body": 0.09}
EXPECTED = {
    "R0": BASE, "R1": {**BASE, "p0_gauge": 3e5}, "R2": {**BASE, "p0_gauge": 7e5},
    "R3": {**BASE, "v_water0": 0.3e-3}, "R4": {**BASE, "v_water0": 0.7e-3},
    "R5": {**BASE, "d_nozzle": 0.015}, "R6": {**BASE, "m_empty": 0.10},
    "R7": {**BASE, "m_empty": 0.25}, "R8": {**BASE, "v_bottle": 1.0e-3, "d_body": 0.079},
    "R9": {**BASE, "v_bottle": 2.0e-3, "d_body": 0.102},
    "E1": {"v_bottle": 1.0e-3, "v_water0": 0.33e-3, "p0_gauge": 7e5, "d_nozzle": 0.022,
           "m_empty": 0.10, "d_body": 0.079, "c_w": CW_STRICH},
    "E2": {"v_bottle": 1.0e-3, "v_water0": 0.33e-3, "p0_gauge": 3e5, "d_nozzle": 0.015,
           "m_empty": 0.25, "d_body": 0.079, "c_w": CW_STRICH},
    "E3": {"v_bottle": 2.0e-3, "v_water0": 0.66e-3, "p0_gauge": 7e5, "d_nozzle": 0.022,
           "m_empty": 0.10, "d_body": 0.102, "c_w": CW_STRICH},
    "E4": {"v_bottle": 2.0e-3, "v_water0": 0.66e-3, "p0_gauge": 3e5, "d_nozzle": 0.015,
           "m_empty": 0.25, "d_body": 0.102, "c_w": CW_STRICH},
}
# Testrakete: bewusst keine der 14 Raketen (kleiner Druck, kurze Rechnung).
TEST_ROCKET = {"v_bottle": 0.5e-3, "v_water0": 0.15e-3, "p0_gauge": 2e5, "d_nozzle": 0.01,
               "m_empty": 0.05, "c_w": 0.4, "d_body": 0.06}
SECRET = 12.3456789  # Testwert; darf nie ausgegeben werden


class TestRaketen(unittest.TestCase):
    def test_14_raketen_wie_in_tool_vergleich_und_stichprobe(self):
        got = dict(run.rockets())
        self.assertEqual(list(got), list(EXPECTED))
        self.assertEqual(got, EXPECTED)

    def test_referenzen_fuer_alle_14(self):
        self.assertEqual(sorted(run.references()), sorted(EXPECTED))

    def test_beta_werte_wie_in_der_notiz(self):
        self.assertEqual((run.CONTROL_BETA, run.BETAS), (1.4, [1.17, 1.20, 1.22]))


class TestExponent(unittest.TestCase):
    def test_setzt_und_stellt_wieder_her(self):
        old_t = simulation.temperature_after_expansion
        with run.exponent(1.2):
            self.assertEqual(waterphase.GAMMA, 1.2)
            self.assertIsNot(simulation.temperature_after_expansion, old_t)
        self.assertEqual(waterphase.GAMMA, 1.4)
        self.assertIs(simulation.temperature_after_expansion, old_t)

    def test_stellt_auch_bei_fehler_wieder_her(self):
        with self.assertRaises(ZeroDivisionError):
            with run.exponent(1.2):
                1 / 0
        self.assertEqual(waterphase.GAMMA, 1.4)

    def test_polytrope_temperatur(self):
        t = run.polytropic_temperature(1.2)(293.15, 2e5, 6e5)
        self.assertAlmostEqual(t, 293.15 * (2e5 / 6e5) ** (0.2 / 1.2), places=12)

    def test_luftstoss_bleibt_bei_1_4(self):
        from app.physics import airphase
        with run.exponent(1.2):
            self.assertEqual(airphase.GAMMA, 1.4)

    def test_kontrolle_ohne_aenderung_gleich_simulate_flight(self):
        direct = simulation.simulate_flight(simulation.RocketConfig(**TEST_ROCKET)).apogee
        self.assertEqual(run.apogee(TEST_ROCKET, 1.4), direct)
        run.apogee(TEST_ROCKET, 1.2)  # danach muss alles wieder wie vorher sein
        self.assertEqual(run.apogee(TEST_ROCKET, 1.4), direct)

    def test_beta_aendert_das_apogaeum(self):
        self.assertNotEqual(run.apogee(TEST_ROCKET, 1.2), run.apogee(TEST_ROCKET, 1.4))


class TestMessung(unittest.TestCase):
    def fake_rockets(self):
        return [("R0", TEST_ROCKET), ("E1", TEST_ROCKET)]

    def test_kontrolle_fehlt_dann_nichts_schreiben(self):
        with mock.patch.object(run, "rockets", self.fake_rockets), \
             mock.patch.object(run, "references", lambda: {"R0": SECRET, "E1": SECRET}), \
             mock.patch.object(run, "apogee", lambda c, b: SECRET + 1), \
             tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(run.main(Path(tmp)), 1)
            self.assertFalse((Path(tmp) / run.VALUES_NAME).exists())
            self.assertNotIn(str(SECRET), out.getvalue())

    def test_schreibt_werte_ohne_ausgabe(self):
        with mock.patch.object(run, "rockets", self.fake_rockets), \
             mock.patch.object(run, "references", lambda: {"R0": SECRET, "E1": SECRET}), \
             mock.patch.object(run, "apogee", lambda c, b: SECRET), \
             tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(run.main(Path(tmp)), 0)
            self.assertNotIn(str(SECRET), out.getvalue())
            with open(Path(tmp) / run.VALUES_NAME, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2 * 4)
            self.assertEqual([r["beta"] for r in rows[:4]], ["1.4", "1.17", "1.2", "1.22"])

    def test_kein_zweiter_lauf(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / run.VALUES_NAME).write_text("x", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run.main(Path(tmp)), 2)


if __name__ == "__main__":
    unittest.main()