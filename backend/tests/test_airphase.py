"""Tests für Phase 2 (Luftstoß)."""

import math

import pytest

from app.physics.airphase import (
    CRITICAL_RATIO,
    R_AIR,
    T_START,
    nozzle_flow,
    simulate_airphase,
    temperature_after_expansion,
)
from app.physics.freeflight import drag_factor
from app.physics.waterphase import GAMMA, P_ATM, nozzle_area

# Beispielrakete für Tests, keine Messwerte
V_BOTTLE = 1.5e-3  # m³
D_NOZZLE = 0.022  # m
M_EMPTY = 0.15  # kg
K_DRAG = drag_factor(c_w=0.5, diameter=0.09)


def test_kritisches_druckverhaeltnis():
    assert CRITICAL_RATIO == pytest.approx(1.893, abs=1e-3)


def test_schub_stetig_an_der_kritischen_grenze():
    # Beide Formeln (verblockt / unterkritisch) müssen an der Grenze übereinstimmen.
    p_crit = CRITICAL_RATIO * P_ATM
    above = nozzle_flow(p_crit * (1 + 1e-9), T_START, D_NOZZLE)
    below = nozzle_flow(p_crit * (1 - 1e-9), T_START, D_NOZZLE)
    assert above[0] == pytest.approx(below[0], rel=1e-6)
    assert above[1] == pytest.approx(below[1], rel=1e-6)


def test_verblockter_massenstrom_wie_lehrbuchformel():
    # mdot = A * p * sqrt(gamma / (R * T)) * (2 / (gamma + 1))^((gamma + 1) / (2 (gamma - 1)))
    p = 4e5
    expected = (
        nozzle_area(D_NOZZLE)
        * p
        * math.sqrt(GAMMA / (R_AIR * T_START))
        * (2 / (GAMMA + 1)) ** ((GAMMA + 1) / (2 * (GAMMA - 1)))
    )
    mdot, _ = nozzle_flow(p, T_START, D_NOZZLE)
    assert mdot == pytest.approx(expected, rel=1e-9)


def test_kein_luftstoss_ohne_ueberdruck():
    r = simulate_airphase(P_ATM, T_START, V_BOTTLE, D_NOZZLE, M_EMPTY, K_DRAG, h0=1.0, v0=30.0)
    assert (r.t_end, r.h_end, r.v_end) == (0.0, 1.0, 30.0)


def test_luftstoss_endet_bei_umgebungsdruck_und_luftmasse_sinkt():
    p_start = 3.4e5
    temp = temperature_after_expansion(T_START, p_start, P_ATM + 5e5)
    r = simulate_airphase(p_start, temp, V_BOTTLE, D_NOZZLE, M_EMPTY, K_DRAG, h0=0.8, v0=36.0)
    assert r.p_end <= P_ATM
    masses = [point[3] for point in r.trajectory]
    assert all(a > b for a, b in zip(masses, masses[1:]))


def test_luftstoss_erhoeht_geschwindigkeit_ohne_luftwiderstand():
    r = simulate_airphase(3.4e5, 250.0, V_BOTTLE, D_NOZZLE, M_EMPTY, 0.0, h0=0.8, v0=36.0)
    assert r.v_end > 36.0