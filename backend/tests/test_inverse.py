"""Tests für den inversen Modus (Startdruck für Zielhöhe)."""

import dataclasses

import pytest

from app.physics.inverse import P_MAX, P_TOL, find_start_pressure
from app.physics.simulation import EXAMPLE_ROCKET, simulate_flight
from app.search.binary_search import BinarySearch


def apogee_at(p):
    return simulate_flight(dataclasses.replace(EXAMPLE_ROCKET, p0_gauge=p)).apogee


@pytest.mark.parametrize("p_true", [2e5, 5e5, 7.5e5])
def test_hin_und_zurueck(p_true):
    # Vorwärts: Druck -> Höhe. Invers: Höhe -> Druck. Muss denselben Druck liefern.
    target = apogee_at(p_true)
    r = find_start_pressure(EXAMPLE_ROCKET, target)
    assert r.converged
    assert r.width <= P_TOL
    assert abs(r.p0_gauge - p_true) <= P_TOL


def test_kontrollflug_trifft_zielhoehe():
    # 1 Pa entspricht bei 5 bar ca. 8e-5 m (Sandbox-Messung); 1 mm ist großzügig.
    r = find_start_pressure(EXAMPLE_ROCKET, 40.0)
    assert r.apogee == pytest.approx(40.0, abs=1e-3)


def test_cfg_wird_nicht_veraendert():
    find_start_pressure(EXAMPLE_ROCKET, 40.0)
    assert EXAMPLE_ROCKET.p0_gauge == 5e5


def test_binaere_suche_liefert_gleichen_druck():
    # Searchable ist austauschbar; beide Verfahren müssen dasselbe Ergebnis liefern.
    r_exp = find_start_pressure(EXAMPLE_ROCKET, 40.0)
    r_bin = find_start_pressure(EXAMPLE_ROCKET, 40.0, searcher=BinarySearch())
    assert abs(r_exp.p0_gauge - r_bin.p0_gauge) <= P_TOL


def test_zielhoehe_nicht_erreichbar():
    unerreichbar = apogee_at(P_MAX) + 1.0
    with pytest.raises(ValueError):
        find_start_pressure(EXAMPLE_ROCKET, unerreichbar)


@pytest.mark.parametrize("target", [0.0, -5.0])
def test_zielhoehe_muss_positiv_sein(target):
    with pytest.raises(ValueError):
        find_start_pressure(EXAMPLE_ROCKET, target)