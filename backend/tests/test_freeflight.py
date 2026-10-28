"""Tests für Phase 3 (Freiflug) gegen analytische Lösungen."""

import math

import pytest

from app.physics.freeflight import G, drag_factor, simulate_freeflight

# Beispielwerte für Tests, keine Messwerte
MASS = 0.15  # kg
DIAMETER = 0.09  # m


@pytest.mark.parametrize("h0, v0", [(0.0, 10.0), (0.0, 30.0), (5.0, 50.0)])
def test_ohne_luftwiderstand_wie_senkrechter_wurf(h0, v0):
    result = simulate_freeflight(h0=h0, v0=v0, mass=MASS, k_drag=0.0)
    assert result.apogee == pytest.approx(h0 + v0**2 / (2 * G), abs=1e-4)
    assert result.t_apogee == pytest.approx(v0 / G, abs=1e-3)


def test_mit_luftwiderstand_wie_analytische_loesung():
    v0 = 30.0
    k = drag_factor(c_w=0.5, diameter=DIAMETER)
    expected = MASS / (2 * k) * math.log(1 + k * v0**2 / (MASS * G))
    result = simulate_freeflight(h0=0.0, v0=v0, mass=MASS, k_drag=k)
    assert result.apogee == pytest.approx(expected, abs=1e-4)


def test_luftwiderstand_senkt_apogaeum():
    k = drag_factor(c_w=0.5, diameter=DIAMETER)
    ohne = simulate_freeflight(h0=0.0, v0=30.0, mass=MASS, k_drag=0.0)
    mit = simulate_freeflight(h0=0.0, v0=30.0, mass=MASS, k_drag=k)
    assert mit.apogee < ohne.apogee


def test_negative_startgeschwindigkeit_wird_abgelehnt():
    with pytest.raises(ValueError):
        simulate_freeflight(h0=0.0, v0=-1.0, mass=MASS, k_drag=0.0)