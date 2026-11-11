"""Tests für run.py (Nachbau, StepEnd, Varianten) ohne die Messraketen auszuwerten.

Die Tests rechnen nur die Beispielrakete des Backends und zwei Testraketen;
die Werte der Messraketen R0 bis R9 werden nicht angesehen.

Start (PowerShell, im Repo-Ordner):
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\\backend:/backend:ro" -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python -W error -m unittest discover -s ereignissuche -v
"""

import contextlib
import csv
import dataclasses
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.physics.simulation import EXAMPLE_ROCKET, RocketConfig, simulate_flight
from app.physics.waterphase import P_ATM, air_pressure
from app.search.binary_search import BinarySearch
from app.search.interpolation_search import InterpolationSearch
from app.search.searchable import Searchable

import run

# Testrakete, deren Druck vor dem Wasser verbraucht ist (Ereignis p = p_atm);
# sie fliegt mit Restwasser in den Freiflug.
PRESSURE_FIRST = RocketConfig(
    v_bottle=1.5e-3, v_water0=1.2e-3, p0_gauge=1.5e5, d_nozzle=0.022,
    m_empty=0.15, c_w=0.345, d_body=0.09,
)
# Zwei kleine Testraketen für measure() (keine Messraketen).
TEST_CHANGES = {"T0": {}, "T1": {"p0_gauge": 3.5e5}}


def load_durchsatz_run():
    """durchsatz/run.py unter anderem Namen laden (beide Dateien heißen run.py)."""
    path = Path(run.__file__).resolve().parent.parent / "durchsatz" / "run.py"
    spec = importlib.util.spec_from_file_location("durchsatz_run", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same(a, b):
    return dataclasses.asdict(a) == dataclasses.asdict(b)


class Plan(unittest.TestCase):
    def test_rockets_equal_durchsatz(self):
        self.assertEqual(run.rockets(), load_durchsatz_run().rockets())

    def test_rocket_order(self):
        self.assertEqual([label for label, _ in run.rockets()], [f"R{i}" for i in range(10)])

    def test_variants_as_in_note(self):
        self.assertEqual(run.VARIANTS, {
            "V0": ("binaer", BinarySearch, BinarySearch),
            "V1": ("interpolation", InterpolationSearch, InterpolationSearch),
            "V2": ("schrittende", run.StepEnd, run.StepEnd),
            "V3": ("schrittende_wasser", run.StepEnd, BinarySearch),
            "V4": ("schrittende_apogaeum", BinarySearch, run.StepEnd),
        })

    def test_nachbau_version(self):
        self.assertEqual(run.NACHBAU_VERSION, "1")


class StepEndTest(unittest.TestCase):
    def test_is_searchable(self):
        self.assertIsInstance(run.StepEnd(), Searchable)

    def test_returns_hi_without_calling_f(self):
        calls = []
        res = run.StepEnd().search(lambda x: calls.append(x) or x, 0.5, 0.0, 1e-3, 1e-12)
        self.assertEqual((res.x, res.evaluations, res.iterations), (1e-3, 0, 0))
        self.assertEqual(res.width, 1e-3)
        self.assertFalse(res.converged)
        self.assertEqual(calls, [])

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            run.StepEnd().search(lambda x: x, 0.0, 1.0, 1.0, 1e-12)


class RecorderTest(unittest.TestCase):
    def test_passes_through_and_records(self):
        rec = run.Recorder(BinarySearch())
        direct = BinarySearch().search(lambda x: x, 0.3, 0.0, 1.0, 1e-9)
        res = rec.search(lambda x: x, 0.3, 0.0, 1.0, 1e-9)
        self.assertEqual(res, direct)
        self.assertEqual(rec.results, [res])


class Nachbau(unittest.TestCase):
    def test_binary_is_bit_identical_example(self):
        res, water, free = run.flight(EXAMPLE_ROCKET, BinarySearch(), BinarySearch())
        self.assertTrue(same(res, simulate_flight(EXAMPLE_ROCKET)))
        self.assertEqual((len(water), len(free)), (1, 1))

    def test_binary_is_bit_identical_pressure_first(self):
        p_empty = air_pressure(0.0, PRESSURE_FIRST.v_bottle, PRESSURE_FIRST.v_water0,
                               PRESSURE_FIRST.p0_gauge + P_ATM)
        self.assertLess(p_empty, P_ATM)  # Testrakete prüft wirklich den anderen Zweig
        res, _, free = run.flight(PRESSURE_FIRST, BinarySearch(), BinarySearch())
        ref = simulate_flight(PRESSURE_FIRST)
        self.assertTrue(same(res, ref))
        self.assertGreater(ref.water_rest, 0.0)  # Restwasser fliegt mit
        self.assertEqual(len(free), 1)  # Freiflug findet statt

    def test_evaluations_match_phase_results(self):
        res, water, free = run.flight(EXAMPLE_ROCKET, BinarySearch(), BinarySearch())
        self.assertGreater(water[0].evaluations, 0)
        self.assertGreater(free[0].evaluations, 0)

    def test_step_end_water_ends_on_step_grid(self):
        ref = simulate_flight(EXAMPLE_ROCKET)
        res, water, _ = run.flight(EXAMPLE_ROCKET, run.StepEnd(), BinarySearch())
        self.assertEqual(water[0].evaluations, 0)
        # Ereignis am Schrittende: Abstand zum vorletzten Punkt der Wasserphase = dt
        water_points = [p for p in res.trajectory if p[0] <= res.t_water_end]
        self.assertAlmostEqual(water_points[-1][0] - water_points[-2][0], 1e-5, places=15)
        self.assertGreaterEqual(res.t_water_end, ref.t_water_end)
        self.assertLess(res.t_water_end - ref.t_water_end, 1e-5)

    def test_step_end_apogee_after_true_apogee(self):
        ref = simulate_flight(EXAMPLE_ROCKET)
        res, _, free = run.flight(EXAMPLE_ROCKET, BinarySearch(), run.StepEnd())
        self.assertEqual(free[0].evaluations, 0)
        self.assertGreaterEqual(res.t_apogee, ref.t_apogee)
        self.assertLess(res.t_apogee - ref.t_apogee, 1e-3)
        # Schub und Brennschluss unverändert, nur das Apogäum-Ereignis verschoben
        self.assertEqual((res.h_burnout, res.v_burnout), (ref.h_burnout, ref.v_burnout))

    def test_step_end_both_changes_result_only_slightly(self):
        # Grobe Plausibilität an der Beispielrakete (keine Messrakete)
        ref = simulate_flight(EXAMPLE_ROCKET)
        res, _, _ = run.flight(EXAMPLE_ROCKET, run.StepEnd(), run.StepEnd())
        self.assertNotEqual(res.apogee, ref.apogee)
        self.assertLess(abs(res.apogee - ref.apogee) / ref.apogee, 1e-2)

    def test_interpolation_runs_and_records(self):
        _, water, free = run.flight(EXAMPLE_ROCKET, InterpolationSearch(),
                                    InterpolationSearch())
        self.assertEqual((len(water), len(free)), (1, 1))
        self.assertGreater(water[0].evaluations, 0)


class SearchCells(unittest.TestCase):
    def test_step_end(self):
        res = run.StepEnd().search(lambda x: x, 0, 0.0, 1.0, 1e-9)
        self.assertEqual(run.search_cells([res], run.StepEnd, "x"), (0, "keine Suche"))

    def test_no_freeflight(self):
        self.assertEqual(run.search_cells([], BinarySearch, "x"), (0, "kein Freiflug"))

    def test_more_than_one_search_raises(self):
        res = BinarySearch().search(lambda x: x, 0.5, 0.0, 1.0, 1e-9)
        with self.assertRaises(RuntimeError):
            run.search_cells([res, res], BinarySearch, "x")

    def test_converged_text(self):
        res = BinarySearch().search(lambda x: x, 0.5, 0.0, 1.0, 1e-9)
        self.assertEqual(run.search_cells([res], BinarySearch, "x"),
                         (res.evaluations, "ja"))


class Measure(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(run, "CHANGES", TEST_CHANGES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_measure(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rows, not_equal = run.measure()
        return rows, not_equal, out.getvalue()

    def test_rows_order_and_bitgleich(self):
        rows, not_equal, out = self.run_measure()
        self.assertEqual([(r["label"], r["variante"]) for r in rows],
                         [(lab, v) for lab in TEST_CHANGES for v in run.VARIANTS])
        self.assertEqual(not_equal, 0)
        self.assertEqual([r["bitgleich"] for r in rows if r["variante"] == "V0"], ["ja", "ja"])
        self.assertTrue(all(r["bitgleich"] == "" for r in rows if r["variante"] != "V0"))
        self.assertEqual(out.count("Ja"), 2)

    def test_step_end_cells(self):
        rows, _, _ = self.run_measure()
        by = {(r["label"], r["variante"]): r for r in rows}
        self.assertEqual(by[("T0", "V2")]["wasser_konvergiert"], "keine Suche")
        self.assertEqual(by[("T0", "V2")]["freiflug_konvergiert"], "keine Suche")
        self.assertEqual(by[("T0", "V3")]["freiflug_konvergiert"], "ja")
        self.assertEqual(by[("T0", "V4")]["wasser_konvergiert"], "ja")

    def test_values_full_precision(self):
        rows, _, _ = self.run_measure()
        cfg = RocketConfig(**{**run.BASE, **TEST_CHANGES["T1"]})
        self.assertEqual(float(rows[5]["apogee"]), simulate_flight(cfg).apogee)

    def test_not_identical_is_reported(self):
        real = run.simulate_flight

        def shifted(cfg):
            res = real(cfg)
            return dataclasses.replace(res, apogee=res.apogee + 1e-12)

        with mock.patch.object(run, "simulate_flight", side_effect=shifted):
            rows, not_equal, out = self.run_measure()
        self.assertEqual(not_equal, 2)
        self.assertIn("Nein", out)
        self.assertEqual([r["bitgleich"] for r in rows if r["variante"] == "V0"],
                         ["nein", "nein"])

    def test_no_values_printed(self):
        rows, _, out = self.run_measure()
        for r in rows:
            for key in ("apogee", "h_burnout", "v_burnout", "t_water_end"):
                self.assertNotIn(r[key], out)
                self.assertNotIn(f"{float(r[key]):.3f}", out)


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        patcher = mock.patch.object(run, "CHANGES", TEST_CHANGES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run.main(self.data)
        return code, out.getvalue()

    def test_writes_csv_with_crlf(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        raw = (self.data / run.VALUES_NAME).read_bytes()
        self.assertIn(b"\r\n", raw)
        with open(self.data / run.VALUES_NAME, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(list(rows[0]), run.COLUMNS)
        self.assertEqual(len(rows), 10)
        self.assertIn("Fertig: 10 Zeilen", out)

    def test_existing_file_aborts(self):
        self.data.mkdir()
        (self.data / run.VALUES_NAME).write_text("x", encoding="utf-8")
        with mock.patch.object(run, "measure") as m:
            code, _ = self.run_main()
        self.assertEqual(code, 2)
        m.assert_not_called()

    def test_other_model_version_aborts(self):
        with mock.patch.object(run, "MODEL_VERSION", "2"), \
                mock.patch.object(run, "measure") as m:
            code, _ = self.run_main()
        self.assertEqual(code, 1)
        m.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_not_identical_returns_3_and_writes(self):
        with mock.patch.object(run, "measure", return_value=([], 1)):
            code, out = self.run_main()
        self.assertEqual(code, 3)
        self.assertTrue((self.data / run.VALUES_NAME).exists())
        self.assertIn("nicht bitgleich", out)

    def test_error_writes_nothing(self):
        with mock.patch.object(run, "measure", side_effect=RuntimeError("x")):
            code, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()