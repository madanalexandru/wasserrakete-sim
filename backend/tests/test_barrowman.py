"""Tests für den Druckpunkt nach Barrowman (app/physics/barrowman.py).

Geometriewerte frei gewählt, NICHT gemessen.
"""

from dataclasses import replace
from math import asin, pi

import pytest

from app.physics.barrowman import (
    center_of_pressure, fins_cn_alpha, fins_cp, nose_cp,
    ogive_radius, volume_of_revolution,
)
from app.physics.simulation import EXAMPLE_ROCKET

D = 0.09  # Rumpfdurchmesser der Beispielrakete

ROCKET = replace(
    EXAMPLE_ROCKET, nose_shape="cone", l_nose=0.12, n_fins=3,
    fin_root_chord=0.10, fin_tip_chord=0.05, fin_span=0.08,
    fin_sweep=0.05, x_fin=0.30,
)


# --- Nase -----------------------------------------------------------------

def test_volume_of_revolution_cone_and_cylinder_exact():
    r, length = D / 2, 0.12
    cone = volume_of_revolution(lambda x: r * x / length, length)
    cylinder = volume_of_revolution(lambda x: r, length)
    assert cone == pytest.approx(pi * r * r * length / 3, rel=1e-12)
    assert cylinder == pytest.approx(pi * r * r * length, rel=1e-12)


def test_cone_cp_two_thirds():
    # Aus Gl. 3-89 mit Kegelvolumen V = A l / 3
    assert nose_cp("cone", 0.12, D) == pytest.approx(0.08)


def test_ogive_shape_tangent_at_body():
    radius = ogive_radius(0.12, D)
    assert radius(0.0) == pytest.approx(0.0, abs=1e-12)  # spitze Nase
    assert radius(0.12) == pytest.approx(D / 2)  # Übergang zum Rumpf
    h = 1e-6  # Steigung am Rumpf ~ 0 (tangential)
    assert (radius(0.12) - radius(0.12 - h)) / h == pytest.approx(0.0, abs=1e-4)


@pytest.mark.parametrize("l_nose", [0.05, 0.12, 0.20])
def test_ogive_volume_is_four_times_printed_eq_3_90(l_nose):
    # Dokumentiert den Fund: Gl. 3-90 (S. 30) wie gedruckt = 1/4 Volumen.
    f = l_nose / D
    area = pi * D * D / 4
    printed = D * area * (
        f * (f * f + 0.25) ** 2 - f ** 3 / 3
        - (f * f - 0.25) * (f * f + 0.25) ** 2 * asin(f / (f * f + 0.25))
    )
    numeric = volume_of_revolution(ogive_radius(l_nose, D), l_nose)
    assert numeric == pytest.approx(4 * printed, rel=1e-9)


def test_ogive_cp_ahead_of_cone_cp():
    # Ogive ist voller als der Kegel -> mehr Volumen -> Druckpunkt weiter vorn
    assert nose_cp("ogive", 0.12, D) < nose_cp("cone", 0.12, D)


# --- Finnen ---------------------------------------------------------------

def test_rectangular_fin_cp_at_quarter_chord():
    # Rechteckfinne ohne Pfeilung: Viertel der Tiefe (S. 6, Text)
    assert fins_cp(0.30, 0.10, 0.10, 0.0) == pytest.approx(0.30 + 0.10 / 4)


def test_four_fins_give_four_thirds_of_three():
    # Gl. 3-11, S. 4: (C_N_alpha)_T = N/2 (C_N_alpha)_1
    args = (0.10, 0.05, 0.08, 0.05, D)
    assert fins_cn_alpha(4, *args) / fins_cn_alpha(3, *args) == pytest.approx(4 / 3)


def test_larger_span_gives_more_normal_force():
    assert fins_cn_alpha(3, 0.10, 0.05, 0.10, 0.05, D) > fins_cn_alpha(3, 0.10, 0.05, 0.08, 0.05, D)


# --- Gesamtrakete ---------------------------------------------------------

def test_total_cp_is_weighted_mean_between_nose_and_fins():
    cp = center_of_pressure(ROCKET)
    assert cp.x_nose < cp.x_cp < cp.x_fins
    expected = (cp.x_nose * cp.cn_nose + cp.x_fins * cp.cn_fins) / (cp.cn_nose + cp.cn_fins)
    assert cp.x_cp == pytest.approx(expected)
    assert cp.cn_nose == 2.0  # Gl. 3-66


def test_bigger_fins_move_cp_aft():
    small = center_of_pressure(ROCKET).x_cp
    big = center_of_pressure(replace(ROCKET, fin_span=0.12)).x_cp
    assert big > small


def test_missing_geometry_names_fields():
    with pytest.raises(ValueError, match="nose_shape"):
        center_of_pressure(EXAMPLE_ROCKET)


@pytest.mark.parametrize("change", [
    {"nose_shape": "kugel"}, {"n_fins": 2}, {"fin_span": 0.0}, {"fin_tip_chord": -0.01},
])
def test_invalid_geometry_rejected(change):
    with pytest.raises(ValueError):
        center_of_pressure(replace(ROCKET, **change))