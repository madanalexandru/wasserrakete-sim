"""Tests für die Stabilitätsprüfung (app/physics/stability.py).

Geometrie- und Massewerte frei gewählt, NICHT gemessen. Die Schwellen in
den Tests sind Testwerte, keine belegte Warnschwelle.
"""

from dataclasses import replace
from math import pi

import pytest

from app.physics.barrowman import center_of_pressure
from app.physics.simulation import EXAMPLE_ROCKET
from app.physics.stability import cg_with_water, check_stability
from app.physics.waterphase import RHO_WATER

D = 0.09  # Rumpfdurchmesser der Beispielrakete

CP_ROCKET = replace(  # nur Druckpunkt-Geometrie, ohne Schwerpunkt
    EXAMPLE_ROCKET, nose_shape="cone", l_nose=0.12, n_fins=3,
    fin_root_chord=0.10, fin_tip_chord=0.05, fin_span=0.08,
    fin_sweep=0.05, x_fin=0.30,
)
ROCKET = replace(CP_ROCKET, x_cg_empty=0.20, l_total=0.42)


def test_empty_cg_is_input():
    assert cg_with_water(ROCKET, 0.0) == 0.20


def test_equal_masses_give_midpoint():
    # Wasser so schwer wie die leere Rakete -> Schwerpunkt genau in der Mitte
    v = ROCKET.m_empty / RHO_WATER
    x_water = ROCKET.l_total - v / (pi * D * D / 4) / 2
    assert cg_with_water(ROCKET, v) == pytest.approx((0.20 + x_water) / 2)


def test_water_moves_cg_toward_tail():
    assert cg_with_water(ROCKET, ROCKET.v_water0) > cg_with_water(ROCKET, 0.0)


def test_margin_definition():
    result = check_stability(ROCKET, min_margin=0.0)
    x_cp = center_of_pressure(ROCKET).x_cp
    assert result.x_cp == x_cp
    assert result.margin_empty == pytest.approx((x_cp - 0.20) / D)
    assert result.margin_start == pytest.approx((x_cp - result.x_cg_start) / D)


def test_stable_rocket_without_warning():
    # Schwerpunkt weit vorn, kein Wasser -> Druckpunkt deutlich dahinter
    cfg = replace(ROCKET, x_cg_empty=0.05, v_water0=0.0)
    result = check_stability(cfg, min_margin=1.0)
    assert result.ok
    assert result.margin_empty > 1.0


def test_warning_below_threshold():
    cfg = replace(ROCKET, x_cg_empty=0.05, v_water0=0.0)
    margin = check_stability(cfg, min_margin=0.0).margin_empty
    result = check_stability(cfg, min_margin=margin + 0.5)
    assert not result.ok
    assert "unter der Schwelle" in result.warnings[0]


def test_unstable_when_cp_ahead_of_cg():
    cfg = replace(ROCKET, x_cg_empty=0.40, v_water0=0.0)
    result = check_stability(cfg, min_margin=0.0)
    assert result.margin_empty < 0
    assert any("instabil" in w for w in result.warnings)


def test_missing_mass_geometry_names_fields():
    with pytest.raises(ValueError, match="x_cg_empty, l_total"):
        check_stability(CP_ROCKET, min_margin=1.0)


@pytest.mark.parametrize("change", [
    {"x_cg_empty": 0.50}, {"x_cg_empty": -0.01}, {"l_total": 0.0},
    {"l_total": 0.05, "x_cg_empty": 0.04},  # Wassersäule länger als Rakete
])
def test_invalid_mass_geometry_rejected(change):
    with pytest.raises(ValueError):
        check_stability(replace(ROCKET, **change), min_margin=1.0)


def test_negative_water_rejected():
    with pytest.raises(ValueError):
        cg_with_water(ROCKET, -1e-4)