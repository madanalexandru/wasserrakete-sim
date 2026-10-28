"""Tests für die Exponentialsuche (Listing 7.10, kontinuierlich übertragen)."""

import pytest

from app.search.binary_search import BinarySearch
from app.search.exponential_search import ExponentialSearch
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


def test_exponentialsuche_ist_searchable():
    assert isinstance(ExponentialSearch(), Searchable)


def test_lineare_funktion():
    # Ziel 7,3 statt 7: x = 3 wäre ein exakter Treffer, dann ist width nicht <= tol
    r = ExponentialSearch(step0=1.0).search(lambda x: 2 * x + 1, 7.3, 0.0, 100.0, TOL)
    assert r.converged
    assert r.width <= TOL
    assert r.x == pytest.approx(3.15, abs=TOL)


def test_nichtlineare_funktion():
    r = ExponentialSearch(step0=0.5).search(lambda x: x**3, 27.5, 0.0, 10.0, TOL)
    assert r.converged
    assert r.x == pytest.approx(27.5 ** (1 / 3), abs=TOL)


def test_ohne_step0_standardschrittweite():
    r = ExponentialSearch().search(lambda x: x, 37.25, 0.0, 100.0, TOL)
    assert r.converged
    assert r.x == pytest.approx(37.25, abs=TOL)


def test_treffer_bei_lo():
    # Listing Z. 7–9
    f = CountingF(lambda x: x)
    r = ExponentialSearch(step0=1.0).search(f, 0.0, 0.0, 10.0, TOL)
    assert r.x == 0.0
    assert r.iterations == 0
    assert r.evaluations == 1 == len(f.calls)


def test_exakter_treffer_waehrend_verdopplung():
    # f(4) == 4: Verdopplung läuft wie im Listing weiter (<=),
    # die binäre Phase erkennt den Treffer am linken Rand.
    r = ExponentialSearch(step0=1.0).search(lambda x: x, 4.0, 0.0, 100.0, TOL)
    assert r.x == 4.0
    assert r.converged


def test_exakter_treffer_bei_hi():
    # Schritte 3, 6, 12 -> auf hi = 10 begrenzt (Listing Z. 17)
    r = ExponentialSearch(step0=3.0).search(lambda x: x, 10.0, 0.0, 10.0, TOL)
    assert r.x == 10.0
    assert r.converged


def test_linke_grenze_ist_letzter_gepruefter_punkt():
    # Anpassung 2: Ziel liegt vor lo + step0. Mit „i / 2“ wäre die linke
    # Grenze lo + step0 / 2 = 0,5 und das Ziel 0,25 läge außerhalb.
    r = ExponentialSearch(step0=1.0).search(lambda x: x, 0.25, 0.0, 10.0, TOL)
    assert r.x == pytest.approx(0.25, abs=TOL)


def test_eingrenzung_verdoppelt():
    # Ziel 5,5: Stellen 1, 2, 4, 8 -> Bereich [4, 8]
    f = CountingF(lambda x: x)
    r = ExponentialSearch(step0=1.0).search(f, 5.5, 0.0, 100.0, 1e-3)
    assert f.calls[:5] == [0.0, 1.0, 2.0, 4.0, 8.0]
    assert all(4.0 <= x <= 8.0 for x in f.calls[5:])
    assert r.x == pytest.approx(5.5, abs=1e-3)


def test_keine_doppelte_auswertung():
    # Anpassung 4: BinarySearch fragt f(prev) und f(x) erneut ab -> Cache
    f = CountingF(lambda x: x**2)
    r = ExponentialSearch(step0=0.1).search(f, 50.0, 0.0, 100.0, 1e-9)
    assert len(f.calls) == len(set(f.calls))
    assert r.evaluations == len(f.calls)


def test_aufwand_haengt_von_position_ab_nicht_von_hi():
    # Kern der Exponentialsuche: O(log i) statt O(log n).
    f = lambda x: x  # noqa: E731
    exp_klein = ExponentialSearch(step0=1.0).search(f, 5.5, 0.0, 1e3, 1e-6)
    exp_gross = ExponentialSearch(step0=1.0).search(f, 5.5, 0.0, 1e12, 1e-6)
    bin_klein = BinarySearch().search(f, 5.5, 0.0, 1e3, 1e-6)
    bin_gross = BinarySearch().search(f, 5.5, 0.0, 1e12, 1e-6)
    assert exp_klein.evaluations == exp_gross.evaluations
    assert bin_gross.evaluations > bin_klein.evaluations
    assert exp_gross.evaluations < bin_gross.evaluations


def test_ziel_bis_hi_nicht_erreichbar():
    # Entspricht „return -1“ in Listing 7.10
    with pytest.raises(ValueError):
        ExponentialSearch(step0=1.0).search(lambda x: x, 50.0, 0.0, 10.0, TOL)


def test_ziel_unter_f_lo():
    with pytest.raises(ValueError):
        ExponentialSearch(step0=1.0).search(lambda x: x, -1.0, 0.0, 10.0, TOL)


@pytest.mark.parametrize("lo, hi, tol", [(1.0, 1.0, TOL), (2.0, 1.0, TOL), (0.0, 1.0, 0.0)])
def test_ungueltige_eingaben(lo, hi, tol):
    with pytest.raises(ValueError):
        ExponentialSearch(step0=0.1).search(lambda x: x, 0.5, lo, hi, tol)


@pytest.mark.parametrize("step0", [0.0, -1.0, float("inf"), float("nan")])
def test_ungueltige_schrittweite(step0):
    with pytest.raises(ValueError):
        ExponentialSearch(step0=step0)