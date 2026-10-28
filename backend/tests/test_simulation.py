"""Tests für den Gesamtflug (alle drei Phasen)."""

from dataclasses import replace

import pytest

from app.physics.freeflight import G
from app.physics.simulation import EXAMPLE_ROCKET, simulate_flight


def test_beispielrakete_liefert_apogaeum():
    r = simulate_flight(EXAMPLE_ROCKET)
    assert r.apogee > r.h_burnout > 0
    assert 0 < r.t_water_end <= r.t_air_end < r.t_apogee


def test_ohne_luftwiderstand_freiflug_wie_senkrechter_wurf():
    # Analytisch ab Brennschluss: h_max = h_b + v_b² / (2 g)
    r = simulate_flight(replace(EXAMPLE_ROCKET, c_w=0.0))
    assert r.apogee == pytest.approx(r.h_burnout + r.v_burnout**2 / (2 * G), abs=1e-4)


def test_luftwiderstand_senkt_apogaeum():
    ohne = simulate_flight(replace(EXAMPLE_ROCKET, c_w=0.0))
    mit = simulate_flight(EXAMPLE_ROCKET)
    assert mit.apogee < ohne.apogee


def test_apogaeum_steigt_mit_startdruck():
    # Voraussetzung für den inversen Modus (Exponentialsuche über den Druck)
    pressures = [2e5, 3e5, 4e5, 5e5, 6e5, 7e5]
    apogees = [simulate_flight(replace(EXAMPLE_ROCKET, p0_gauge=p)).apogee for p in pressures]
    assert all(a < b for a, b in zip(apogees, apogees[1:]))


def test_restwasser_ohne_luftstoss():
    r = simulate_flight(replace(EXAMPLE_ROCKET, v_water0=1.4e-3, p0_gauge=1e5))
    assert r.water_rest > 0
    assert r.t_air_end == r.t_water_end


def test_flugbahn_zeitlich_geordnet():
    times = [point[0] for point in simulate_flight(EXAMPLE_ROCKET).trajectory]
    assert all(a < b for a, b in zip(times, times[1:]))