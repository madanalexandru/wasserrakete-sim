"""Tests für die Interpolationssuche (Listing 7.9, kontinuierlich übertragen)."""

import math

import pytest

from app.physics.freeflight import drag_factor, simulate_freeflight
from app.physics.inverse import P_TOL, find_start_pressure
from app.physics.simulation import EXAMPLE_ROCKET
from app.physics.waterphase import simulate_waterphase
from app.search.binary_search import BinarySearch
from app.search.interpolation_search import InterpolationSearch
from app.search.searchable import Searchable

TOL = 1e-12


class CountingF:
    """Zählt jeden Aufruf von f und merkt sich die ausgewerteten Stellen."""

    def __init__(self, f):
        self.f = f
        self.calls = []

    def __call__(self, x):
        self.calls.append(x)
        return self.f(x)


def test_interpolationssuche_ist_searchable():
    assert isinstance(InterpolationSearch(), Searchable)


# --- Grundverhalten ---

def test_lineare_funktion_erste_schaetzung_trifft():
    # Bei einer Geraden ist die Interpolation exakt: höchstens 2 Schätzungen
    r = InterpolationSearch().search(lambda x: 2 * x + 1, 7.3, 0.0, 10.0, TOL)
    assert r.converged
    assert r.x == pytest.approx(3.15, abs=TOL)
    assert r.iterations <= 2


def test_steigende_nichtlineare_funktion():
    r = InterpolationSearch().search(lambda x: x**3, 1.2345, 0.0, 2.0, TOL)
    assert r.converged
    assert r.x == pytest.approx(1.2345 ** (1 / 3), abs=TOL)


def test_fallende_funktion():
    # Wie v(t) beim Apogäum: fällt, Nullstelle gesucht
    r = InterpolationSearch().search(math.cos, 0.0, 0.0, math.pi, TOL)
    assert r.converged
    assert r.x == pytest.approx(math.pi / 2, abs=TOL)


def test_treffer_am_rand():
    r = InterpolationSearch().search(lambda x: x, 0.0, 0.0, 2.0, TOL)
    assert r.x == 0.0
    assert r.iterations == 0


def test_treffer_am_rechten_rand():
    r = InterpolationSearch().search(lambda x: x, 2.0, 0.0, 2.0, TOL)
    assert r.x == 2.0
    assert r.iterations == 0


def test_ziel_ausserhalb_wirft_fehler():
    # Entspricht "return -1" in Listing 7.9
    with pytest.raises(ValueError):
        InterpolationSearch().search(lambda x: x, 5.0, 0.0, 2.0, TOL)


@pytest.mark.parametrize("lo, hi, tol", [(1.0, 1.0, TOL), (2.0, 1.0, TOL), (0.0, 1.0, 0.0)])
def test_ungueltige_eingaben(lo, hi, tol):
    with pytest.raises(ValueError):
        InterpolationSearch().search(lambda x: x, 0.5, lo, hi, tol)


# --- Die zwei Fehler aus Listing 7.9, Zeile 11 ---

def test_fix1_erst_multiplizieren_dann_teilen():
    # Wertebereich (1000) viel größer als Intervall (1): Im Listing ergäbe
    # (high - low) / (Wertebereich) als Ganzzahl 0, die Schätzung bliebe bei lo.
    f = CountingF(lambda x: 1000 * x)
    InterpolationSearch().search(f, 700.0, 0.0, 1.0, TOL)
    erste_schaetzung = f.calls[2]  # calls[0], calls[1] = Randwerte
    assert erste_schaetzung == pytest.approx(0.7, abs=1e-12)


def test_fix2_gleiche_randwerte_keine_division_durch_null():
    # Wie [5] oder [5, 5, 5] im Listing: dort ArithmeticException
    konstant = lambda x: 5.0  # noqa: E731
    r = InterpolationSearch().search(konstant, 5.0, 0.0, 1.0, TOL)
    assert r.x == 0.0
    with pytest.raises(ValueError):  # nicht ZeroDivisionError
        InterpolationSearch().search(konstant, 6.0, 0.0, 1.0, TOL)


# --- Kontinuierlicher Fall: Stehenbleiben einer Grenze ---

def test_ohne_illinois_bleibt_eine_grenze_stehen():
    # x^3 ist konvex: Die Schätzung liegt immer links vom Ziel, nur lo rückt.
    f = CountingF(lambda x: x**3)
    r = InterpolationSearch(max_iter=30, illinois=False).search(f, 1.2345, 0.0, 2.0, TOL)
    ziel = 1.2345 ** (1 / 3)
    assert all(x < ziel for x in f.calls[2:])  # hi = 2 wird nie ersetzt
    assert not r.converged
    assert r.width > 0.5


def test_mit_illinois_ruecken_beide_grenzen():
    # 1 - e^(-x) ist gekrümmt; Abbruch hier über die Breite, nicht durch Treffer
    f = CountingF(lambda x: 1 - math.exp(-x))
    r = InterpolationSearch().search(f, 0.4321, 0.0, 10.0, TOL)
    ziel = -math.log(1 - 0.4321)
    assert any(x < ziel for x in f.calls[2:])
    assert any(x > ziel for x in f.calls[2:])
    assert r.width <= TOL
    assert r.x == pytest.approx(ziel, abs=TOL)


def test_illinois_braucht_weniger_auswertungen_als_ohne():
    f = lambda x: x**3  # noqa: E731
    mit = InterpolationSearch().search(f, 1.2345, 0.0, 2.0, TOL)
    ohne = InterpolationSearch(illinois=False).search(f, 1.2345, 0.0, 2.0, TOL)
    assert mit.evaluations < ohne.evaluations


# --- Abbruch ---

def test_zu_kleine_toleranz_bricht_trotzdem_ab():
    r = InterpolationSearch().search(lambda x: x**3, 0.5, 0.0, 1.0, 1e-30)
    assert r.iterations < 200
    assert r.x == pytest.approx(0.5 ** (1 / 3), abs=1e-15)


def test_max_iter_meldet_nicht_konvergiert():
    r = InterpolationSearch(max_iter=2).search(lambda x: x**3, 1.2345, 0.0, 2.0, TOL)
    assert r.iterations == 2
    assert not r.converged


def test_auswertungen_gleich_schaetzungen_plus_raender():
    r = InterpolationSearch().search(lambda x: x**3, 1.2345, 0.0, 2.0, TOL)
    assert r.evaluations == r.iterations + 2


# --- Austauschbar als searcher: Apogäum, Wasser-Ende, inverser Modus ---

def test_apogaeum_gleich_wie_binaere_suche():
    k = drag_factor(c_w=0.5, diameter=0.09)
    a = simulate_freeflight(h0=0.0, v0=30.0, mass=0.15, k_drag=k)
    b = simulate_freeflight(
        h0=0.0, v0=30.0, mass=0.15, k_drag=k, searcher=InterpolationSearch()
    )
    assert b.t_apogee == pytest.approx(a.t_apogee, abs=1e-11)
    assert b.apogee == pytest.approx(a.apogee, abs=1e-9)
    assert b.trajectory[-1][2] == 0.0


def test_wasser_ende_gleich_wie_binaere_suche():
    k = drag_factor(c_w=0.5, diameter=0.09)
    args = (1.5e-3, 0.5e-3, 5e5, 0.022, 0.15, k)
    a = simulate_waterphase(*args)
    b = simulate_waterphase(*args, searcher=InterpolationSearch())
    assert b.t_end == pytest.approx(a.t_end, abs=1e-11)
    assert b.water_rest == 0.0


def test_inverser_modus_gleicher_druck_wie_binaere_suche():
    r_int = find_start_pressure(EXAMPLE_ROCKET, 40.0, searcher=InterpolationSearch())
    r_bin = find_start_pressure(EXAMPLE_ROCKET, 40.0, searcher=BinarySearch())
    assert r_int.converged
    assert r_int.width <= P_TOL
    assert abs(r_int.p0_gauge - r_bin.p0_gauge) <= P_TOL