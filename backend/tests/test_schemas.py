"""Tests für die API-Schemas (app/schemas.py).

Geometrie- und Massewerte wie in test_stability.py frei gewählt, NICHT
gemessen. Geprüft wird nur, ob gültige Eingaben durchkommen und ungültige
mit einem ValidationError (in der API: 422) abgelehnt werden.
"""

from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from math import inf, nan, pi

import pytest
from pydantic import ValidationError

from app.models import CONFIG_FIELDS, GEOMETRY_FIELDS
from app.physics.airphase import T_START
from app.physics.barrowman import check_geometry
from app.physics.simulation import EXAMPLE_ROCKET, simulate_flight
from app.physics.stability import (
    StabilityValues, cg_with_water, check_mass_geometry, stability_values,
)
from app.physics.waterphase import simulate_waterphase
from app.schemas import RocketCreate, RocketRead, StabilityRead

GEOMETRY = dict(
    nose_shape="cone", l_nose=0.12, n_fins=3, fin_root_chord=0.10,
    fin_tip_chord=0.05, fin_span=0.08, fin_sweep=0.05, x_fin=0.30,
    x_cg_empty=0.20, l_total=0.42,
)
MINIMAL = {"name": "Testrakete", **asdict(EXAMPLE_ROCKET)}
FULL = {**MINIMAL, **GEOMETRY}


def make(**changes) -> RocketCreate:
    return RocketCreate(**{**FULL, **changes})


def error_text(exc_info) -> str:
    return str(exc_info.value)


# --- Übereinstimmung mit Datenmodell und Physik ---------------------------

def test_create_fields_match_model():
    assert list(RocketCreate.model_fields) == ["name", *CONFIG_FIELDS]


def test_read_fields_match_model():
    # stability ist berechnet, nicht gespeichert (Entscheidung 3B/7a)
    assert list(RocketRead.model_fields) == [
        "id", "name", "created_at", *CONFIG_FIELDS, "stability",
    ]


def test_stability_read_fields_match_physics():
    assert list(StabilityRead.model_fields) == [f.name for f in fields(StabilityValues)]


def test_stability_read_takes_values_from_physics():
    values = stability_values(make().to_config())
    assert StabilityRead.model_validate(values).model_dump() == asdict(values)


def test_rocket_read_stability_defaults_to_none():
    config = {k: v for k, v in FULL.items() if k != "name"}
    read = RocketRead(id=1, name="x", created_at=datetime.now(timezone.utc), **config)
    assert read.stability is None


def test_to_config_roundtrip():
    rocket = make()
    assert asdict(rocket.to_config()) == {k: v for k, v in FULL.items() if k != "name"}


# --- Gültige Eingaben -----------------------------------------------------

def test_minimal_rocket_without_geometry_is_valid():
    rocket = RocketCreate(**MINIMAL)
    assert all(getattr(rocket, name) is None for name in GEOMETRY_FIELDS)


def test_geometry_keys_may_be_omitted():
    # Ein Client schickt die Geometrie-Schlüssel gar nicht erst mit.
    data = {k: v for k, v in MINIMAL.items() if k not in GEOMETRY_FIELDS}
    assert RocketCreate(**data).l_total is None


def test_full_rocket_is_valid():
    assert make().n_fins == 3


def test_temp0_defaults_to_physics_constant():
    data = {k: v for k, v in MINIMAL.items() if k != "temp0"}
    assert RocketCreate(**data).temp0 == T_START


def test_c_w_zero_allowed():
    assert make(c_w=0.0).c_w == 0.0


def test_fin_tip_chord_zero_allowed():
    assert make(fin_tip_chord=0.0).fin_tip_chord == 0.0


# --- Einzelne Felder ------------------------------------------------------

@pytest.mark.parametrize("field", [
    "v_bottle", "v_water0", "p0_gauge", "d_nozzle", "m_empty", "d_body",
    "temp0", "l_nose", "fin_root_chord", "fin_span", "l_total",
])
@pytest.mark.parametrize("value", [0.0, -1.0])
def test_must_be_positive(field, value):
    with pytest.raises(ValidationError) as exc:
        make(**{field: value})
    assert field in error_text(exc)


@pytest.mark.parametrize("field", ["c_w", "fin_tip_chord", "x_fin", "x_cg_empty"])
def test_must_not_be_negative(field):
    with pytest.raises(ValidationError) as exc:
        make(**{field: -0.01})
    assert field in error_text(exc)


@pytest.mark.parametrize("n", [2, 5])
def test_n_fins_only_3_or_4(n):
    with pytest.raises(ValidationError):
        make(n_fins=n)


def test_unknown_nose_shape_rejected():
    with pytest.raises(ValidationError):
        make(nose_shape="parabolic")


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        make(name="")


@pytest.mark.parametrize("value", [nan, inf])
def test_nan_and_inf_rejected(value):
    with pytest.raises(ValidationError):
        make(p0_gauge=value)


def test_unknown_field_rejected():
    with pytest.raises(ValidationError) as exc:
        make(fin_sweeep=0.05)  # Tippfehler
    assert "fin_sweeep" in error_text(exc)


# --- Regeln über mehrere Felder -------------------------------------------

@pytest.mark.parametrize("v_water0", [1.5e-3, 2.0e-3])  # gleich und größer als v_bottle
def test_water_must_be_less_than_bottle(v_water0):
    with pytest.raises(ValidationError) as exc:
        make(v_water0=v_water0)
    assert "v_water0" in error_text(exc)


@pytest.mark.parametrize("d_nozzle", [0.09, 0.10])
def test_nozzle_must_be_narrower_than_body(d_nozzle):
    with pytest.raises(ValidationError) as exc:
        make(d_nozzle=d_nozzle)
    assert "d_nozzle" in error_text(exc)


@pytest.mark.parametrize("missing", GEOMETRY_FIELDS)
def test_partial_geometry_rejected(missing):
    with pytest.raises(ValidationError) as exc:
        make(**{missing: None})
    assert "unvollständig" in error_text(exc)
    assert missing in error_text(exc)


def test_single_geometry_field_rejected():
    with pytest.raises(ValidationError):
        RocketCreate(**{**MINIMAL, "n_fins": 4})


def test_cg_outside_rocket_rejected():
    with pytest.raises(ValidationError) as exc:
        make(x_cg_empty=0.50)  # l_total = 0.42
    assert "x_cg_empty" in error_text(exc)


def test_water_column_longer_than_rocket_rejected():
    # 1 l in 9 cm Rumpf -> Säule ≈ 0,157 m; Rakete nur 0,10 m lang
    height = 1.0e-3 / (pi * 0.09 ** 2 / 4)
    assert height > 0.10
    with pytest.raises(ValidationError) as exc:
        make(v_water0=1.0e-3, l_total=0.10, x_cg_empty=0.05, l_nose=0.05, x_fin=0.0)
    assert "Wassersäule" in error_text(exc)


# --- Schema und Physik laufen nicht auseinander (Entscheidung C) ----------
# Was das Schema ablehnt, lehnt auch die Physik ab, und umgekehrt.

def test_physics_rejects_water_not_less_than_bottle():
    with pytest.raises(ValueError):
        simulate_waterphase(1.5e-3, 1.5e-3, 5e5, 0.022, 0.15, 0.0)


def test_physics_rejects_cg_outside_rocket():
    with pytest.raises(ValueError):
        check_mass_geometry(replace(EXAMPLE_ROCKET, **{**GEOMETRY, "x_cg_empty": 0.50}))


def test_physics_rejects_long_water_column():
    cfg = replace(EXAMPLE_ROCKET, **{**GEOMETRY, "l_total": 0.10, "x_cg_empty": 0.05})
    with pytest.raises(ValueError):
        cg_with_water(cfg, 1.0e-3)


@pytest.mark.parametrize("change", [{"n_fins": 5}, {"nose_shape": "parabolic"},
                                    {"fin_span": 0.0}, {"x_fin": -0.01}])
def test_physics_rejects_same_geometry_as_schema(change):
    with pytest.raises(ValueError):
        check_geometry(replace(EXAMPLE_ROCKET, **{**GEOMETRY, **change}))
    with pytest.raises(ValidationError):
        make(**change)


def test_valid_schema_runs_in_physics():
    cfg = make().to_config()
    check_geometry(cfg)
    check_mass_geometry(cfg)
    assert simulate_flight(cfg).apogee > 0


# --- Extreme Werte: 422 statt 500 (Entscheidung 9x) -----------------------
# Laut Feldgrenzen gültig, aber nicht endlich berechenbar. Vorher stürzte
# das Schema bei d_body = 1e-200 mit ZeroDivisionError ab (API: 500,
# Sandbox 02.11.). Werte wie in test_stability.py.

ABSURD = [
    {"fin_sweep": 1e200},
    {"fin_sweep": -1e200},
    {"fin_span": 1e-300},
    {"d_body": 1e-200, "d_nozzle": 1e-201},
    {"nose_shape": "ogive", "l_nose": 1e200},
    {"fin_span": 1e200},
    {"fin_root_chord": 1e300, "fin_tip_chord": 1e300},
    {"x_fin": 1.7e308},
]


@pytest.mark.parametrize("change", ABSURD)
def test_absurd_values_rejected_by_schema_and_physics(change):
    with pytest.raises(ValueError, match="nicht berechenbar"):
        stability_values(replace(EXAMPLE_ROCKET, **{**GEOMETRY, **change}))
    with pytest.raises(ValidationError) as exc:
        make(**change)
    assert "nicht berechenbar" in error_text(exc)