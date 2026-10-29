"""Tests für die optionalen Geometriefelder in RocketConfig (Barrowman)."""

from dataclasses import fields, replace

from app.physics.simulation import EXAMPLE_ROCKET, RocketConfig, simulate_flight

GEOMETRY_FIELDS = [
    "nose_shape", "l_nose", "n_fins", "fin_root_chord", "fin_tip_chord",
    "fin_span", "fin_sweep", "x_fin", "x_cg_empty", "l_total",
]


def test_geometry_fields_exist_and_default_to_none():
    names = [f.name for f in fields(RocketConfig)]
    for name in GEOMETRY_FIELDS:
        assert name in names
        assert getattr(EXAMPLE_ROCKET, name) is None


def test_old_configs_still_work_without_geometry():
    # Bisherige Aufrufe ohne Finnen/Nase bleiben gültig.
    cfg = RocketConfig(1.5e-3, 0.5e-3, 5e5, 0.022, 0.15, 0.5, 0.09)
    assert cfg.n_fins is None


def test_geometry_does_not_change_flight():
    # Barrowman ist nur eine Prüfung: Die Flugbahn bleibt identisch.
    # Werte frei gewählt, NICHT gemessen.
    with_geometry = replace(
        EXAMPLE_ROCKET, nose_shape="cone", l_nose=0.12, n_fins=3,
        fin_root_chord=0.10, fin_tip_chord=0.05, fin_span=0.08,
        fin_sweep=0.05, x_fin=0.30, x_cg_empty=0.25, l_total=0.42,
    )
    assert simulate_flight(with_geometry).apogee == simulate_flight(EXAMPLE_ROCKET).apogee