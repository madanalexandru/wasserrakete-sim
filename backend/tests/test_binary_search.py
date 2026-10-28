"""Tests für das Searchable-Interface und die binäre Suche."""

import math

import pytest

from app.search.binary_search import BinarySearch
from app.search.searchable import Searchable

TOL = 1e-12


def test_binaere_suche_ist_searchable():
    assert isinstance(BinarySearch(), Searchable)


def test_interface_nicht_direkt_instanziierbar():
    with pytest.raises(TypeError):
        Searchable()


def test_lineare_funktion():
    r = BinarySearch().search(lambda x: 2 * x + 1, 5.0, 0.0, 10.0, TOL)
    assert r.converged
    assert r.x == pytest.approx(2.0, abs=TOL)


def test_steigende_nichtlineare_funktion():
    r = BinarySearch().search(lambda x: x**3, 2.0, 0.0, 2.0, TOL)
    assert r.x == pytest.approx(2 ** (1 / 3), abs=TOL)


def test_fallende_funktion():
    # Wie v(t) beim Apogäum: fällt, Nullstelle gesucht
    r = BinarySearch().search(math.cos, 0.0, 0.0, math.pi, TOL)
    assert r.x == pytest.approx(math.pi / 2, abs=TOL)


def test_exakter_treffer_in_der_mitte():
    r = BinarySearch().search(lambda x: x, 1.0, 0.0, 2.0, TOL)
    assert r.x == 1.0
    assert r.iterations == 1


def test_treffer_am_rand():
    r = BinarySearch().search(lambda x: x, 0.0, 0.0, 2.0, TOL)
    assert r.x == 0.0
    assert r.iterations == 0


def test_ziel_ausserhalb_wirft_fehler():
    # Entspricht "return -1" in Listing 7.8
    with pytest.raises(ValueError):
        BinarySearch().search(lambda x: x, 5.0, 0.0, 2.0, TOL)


@pytest.mark.parametrize("lo, hi, tol", [(1.0, 1.0, TOL), (2.0, 1.0, TOL), (0.0, 1.0, 0.0)])
def test_ungueltige_eingaben(lo, hi, tol):
    with pytest.raises(ValueError):
        BinarySearch().search(lambda x: x, 0.5, lo, hi, tol)


def test_schrittzahl_logarithmisch():
    # O(log n): Anzahl Halbierungen = ceil(log2(Breite / tol))
    width, tol = 1.0, 1e-9
    r = BinarySearch().search(lambda x: x, math.pi / 4, 0.0, width, tol)
    assert r.iterations == math.ceil(math.log2(width / tol))
    assert r.evaluations == r.iterations + 2


def test_zu_kleine_toleranz_bricht_trotzdem_ab():
    # tol unter der Maschinengenauigkeit: keine Endlosschleife
    r = BinarySearch().search(lambda x: x, math.pi / 4, 0.0, 1.0, 1e-30)
    assert r.iterations < 200
    assert r.x == pytest.approx(math.pi / 4, abs=1e-15)


def test_max_iter_meldet_nicht_konvergiert():
    r = BinarySearch(max_iter=5).search(lambda x: x, math.pi / 4, 0.0, 1.0, TOL)
    assert r.iterations == 5
    assert not r.converged