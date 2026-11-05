"""Tests für die Schemas der Experimentserie (app/schemas.py).

Geprüft wird: welche Eingaben eine Serie beschreiben dürfen, welche Werte
daraus entstehen, dass jeder Schritt vorab dieselben Regeln wie
RocketCreate erfüllen muss und welche Regeln im inversen Modus gelten.
Werte frei gewählt, NICHT gemessen.
"""

from dataclasses import replace
from datetime import datetime, timezone
from math import inf, nan, nextafter
from typing import get_args

import pytest
from pydantic import ValidationError

from app.models import CONFIG_FIELDS, GEOMETRY_FIELDS, REQUIRED_CONFIG_FIELDS, Series
from app.physics.inverse import P_MAX, P_MIN, P_TOL
from app.physics.simulation import EXAMPLE_ROCKET
from app.schemas import (
    DEFAULT_SEARCHER, FLIGHTS_PER_INVERSE_STEP, INVERSE_PARAM, SEARCHERS,
    SERIES_MAX_STEPS, SERIES_MAX_STEPS_INVERSE, RocketCreate, SeriesCreate,
    SeriesRead, SeriesStepError,
)
from app.search.binary_search import BinarySearch

GEOMETRY = dict(
    nose_shape="cone", l_nose=0.12, n_fins=3, fin_root_chord=0.10,
    fin_tip_chord=0.05, fin_span=0.08, fin_sweep=0.05, x_fin=0.30,
    x_cg_empty=0.20, l_total=0.42,
)
VALID = dict(
    name="Druckserie", mode="forward", param_name="p0_gauge",
    param_start=2e5, param_stop=6e5, n_steps=5,
)
INVERSE = dict(
    name="Zielhoehen", mode="inverse", param_name="target_apogee",
    param_start=10.0, param_stop=40.0, n_steps=4,
)


def make(**changes) -> SeriesCreate:
    return SeriesCreate(**{**VALID, **changes})


def make_inverse(**changes) -> SeriesCreate:
    return SeriesCreate(**{**INVERSE, **changes})


# --- Übereinstimmung mit Datenmodell und RocketCreate ----------------------

def test_variable_params_are_the_required_config_fields_and_the_target():
    allowed = get_args(SeriesCreate.model_fields["param_name"].annotation)
    assert allowed == (*REQUIRED_CONFIG_FIELDS, INVERSE_PARAM)


def test_inverse_param_is_a_flight_column():
    # Die CSV sortiert nach der Spalte mit dem Namen param_name
    assert INVERSE_PARAM in Series.metadata.tables["flights"].columns.keys()


def test_searchers_match_the_schema():
    literal = get_args(SeriesCreate.model_fields["searcher"].annotation)[0]
    assert get_args(literal) == SEARCHERS
    assert DEFAULT_SEARCHER in SEARCHERS


def test_variable_params_exist_in_rocketcreate():
    assert set(REQUIRED_CONFIG_FIELDS) <= set(RocketCreate.model_fields)


def test_every_input_field_has_a_series_column():
    assert set(SeriesCreate.model_fields) <= set(Series.__table__.columns.keys())


def test_read_fields_are_the_series_columns_in_order():
    assert list(SeriesRead.model_fields) == list(Series.__table__.columns.keys())


# --- Gültige Eingaben --------------------------------------------------------

def test_valid_series_is_accepted():
    s = make()
    assert s.param_name == "p0_gauge"
    assert s.n_steps == 5


@pytest.mark.parametrize("param", REQUIRED_CONFIG_FIELDS)
def test_every_required_field_can_be_varied(param):
    assert make(param_name=param, param_start=0.1, param_stop=0.2).param_name == param


def test_values_are_linear_and_inclusive():
    assert make().param_values() == [2e5, 3e5, 4e5, 5e5, 6e5]


def test_first_and_last_value_are_exact():
    values = make(param_start=0.1, param_stop=0.7, n_steps=7).param_values()
    assert len(values) == 7
    assert values[0] == 0.1
    assert values[-1] == 0.7


def test_two_steps_give_start_and_stop():
    assert make(n_steps=2).param_values() == [2e5, 6e5]


def test_max_steps_is_allowed():
    assert len(make(n_steps=SERIES_MAX_STEPS).param_values()) == SERIES_MAX_STEPS


# --- Ungültige Eingaben ------------------------------------------------------

@pytest.mark.parametrize("n", [1, 0, -3, SERIES_MAX_STEPS + 1])
def test_n_steps_outside_limits_is_rejected(n):
    with pytest.raises(ValidationError):
        make(n_steps=n)


@pytest.mark.parametrize("param", [*GEOMETRY_FIELDS, "name", "p0"])
def test_other_params_are_rejected(param):
    with pytest.raises(ValidationError):
        make(param_name=param)


@pytest.mark.parametrize("start, stop", [(6e5, 2e5), (4e5, 4e5)])
def test_start_must_be_below_stop(start, stop):
    with pytest.raises(ValidationError, match="param_start muss kleiner"):
        make(param_start=start, param_stop=stop)


@pytest.mark.parametrize("field", ["param_start", "param_stop"])
@pytest.mark.parametrize("bad", [nan, inf, -inf])
def test_nan_and_inf_are_rejected(field, bad):
    with pytest.raises(ValidationError):
        make(**{field: bad})


def test_overflowing_range_is_rejected():
    # Spanne 2e308 ist größer als die größte Gleitkommazahl -> unendlich
    with pytest.raises(ValidationError, match="nicht endlich"):
        make(param_start=-1e308, param_stop=1e308, n_steps=3)


def test_indistinguishable_steps_are_rejected():
    # Start und Stopp nur eine Rundungsstufe auseinander -> gleiche Werte
    with pytest.raises(ValidationError, match="nicht streng steigend"):
        make(param_start=1.0, param_stop=nextafter(1.0, 2.0), n_steps=3)


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        make(searchr="binary")


def test_target_is_not_allowed_in_forward_mode():
    with pytest.raises(ValidationError, match="nur im inversen Modus erlaubt"):
        make(param_name="target_apogee", param_start=10.0, param_stop=40.0)


def test_searcher_is_not_allowed_in_forward_mode():
    with pytest.raises(ValidationError, match="searcher ist nur im inversen Modus"):
        make(searcher="binary")


def test_forward_mode_accepts_explicit_null_searcher():
    # null entspricht der Antwort SeriesRead im Vorwärtsmodus
    assert make(searcher=None).searcher is None


def test_inverse_step_limit_does_not_apply_to_forward_mode():
    assert make(n_steps=SERIES_MAX_STEPS_INVERSE + 1).n_steps == SERIES_MAX_STEPS_INVERSE + 1


def test_empty_name_is_rejected():
    with pytest.raises(ValidationError):
        make(name="")


@pytest.mark.parametrize("field", list(VALID))
def test_every_input_field_is_required(field):
    data = {k: v for k, v in VALID.items() if k != field}
    with pytest.raises(ValidationError):
        SeriesCreate(**data)


# --- Inverser Modus ------------------------------------------------------------

def test_inverse_series_gets_the_default_searcher():
    s = make_inverse()
    assert s.searcher == DEFAULT_SEARCHER == "exponential"
    # wird mitgespeichert, weil main.py die Serie aus model_dump() anlegt
    assert s.model_dump()["searcher"] == DEFAULT_SEARCHER


@pytest.mark.parametrize("searcher", SEARCHERS)
def test_every_searcher_is_accepted(searcher):
    assert make_inverse(searcher=searcher).searcher == searcher


@pytest.mark.parametrize("searcher", ["interpolation_no_illinois", "Binary", "", "bisection"])
def test_unknown_searcher_is_rejected(searcher):
    with pytest.raises(ValidationError):
        make_inverse(searcher=searcher)


@pytest.mark.parametrize("param", REQUIRED_CONFIG_FIELDS)
def test_inverse_mode_needs_the_target(param):
    with pytest.raises(ValidationError, match="muss param_name target_apogee sein"):
        make_inverse(param_name=param)


@pytest.mark.parametrize("start", [0.0, -5.0])
def test_targets_must_be_positive(start):
    with pytest.raises(ValidationError, match="Zielhöhen müssen > 0 m sein"):
        make_inverse(param_start=start)


def test_small_positive_target_is_accepted():
    # Ob die Höhe erreichbar ist, entscheidet erst die Physik im Endpunkt
    assert make_inverse(param_start=1e-9).param_start == 1e-9


def test_inverse_max_steps_is_allowed():
    assert make_inverse(n_steps=SERIES_MAX_STEPS_INVERSE).n_steps == SERIES_MAX_STEPS_INVERSE


def test_inverse_more_steps_are_rejected():
    with pytest.raises(ValidationError, match=f"höchstens {SERIES_MAX_STEPS_INVERSE} Schritte"):
        make_inverse(n_steps=SERIES_MAX_STEPS_INVERSE + 1)


def test_flights_per_inverse_step_match_the_binary_search():
    # Lineare Testfunktion ohne exakten Treffer: Aufrufe der binären Suche
    # = 2 Randwerte + Halbierungen; dazu Kontroll- und Ergebnisflug.
    target = P_MIN + 0.3 * (P_MAX - P_MIN) + 0.123
    r = BinarySearch().search(lambda p: p, target, P_MIN, P_MAX, P_TOL)
    assert r.converged
    assert r.evaluations + 2 == FLIGHTS_PER_INVERSE_STEP


def test_inverse_limit_keeps_the_flight_budget():
    assert SERIES_MAX_STEPS_INVERSE * FLIGHTS_PER_INVERSE_STEP <= SERIES_MAX_STEPS


def test_target_values_are_linear_and_inclusive():
    assert make_inverse().param_values() == [10.0, 20.0, 30.0, 40.0]


def test_step_configs_are_only_for_forward_mode():
    with pytest.raises(RuntimeError, match="nur für den Vorwärtsmodus"):
        make_inverse().step_configs(EXAMPLE_ROCKET)


# --- Vorabprüfung jedes Schritts ---------------------------------------------

def test_step_configs_change_only_the_param():
    configs = make().step_configs(EXAMPLE_ROCKET)
    assert [c.p0_gauge for c in configs] == [2e5, 3e5, 4e5, 5e5, 6e5]
    for c in configs:
        assert replace(c, p0_gauge=EXAMPLE_ROCKET.p0_gauge) == EXAMPLE_ROCKET


def test_step_configs_keep_geometry():
    rocket = replace(EXAMPLE_ROCKET, **GEOMETRY)
    configs = make(param_name="c_w", param_start=0.3, param_stop=0.7, n_steps=3).step_configs(rocket)
    for c in configs:
        assert all(getattr(c, f) == getattr(rocket, f) for f in CONFIG_FIELDS if f != "c_w")


def test_step_configs_do_not_change_the_rocket():
    before = replace(EXAMPLE_ROCKET)
    make().step_configs(EXAMPLE_ROCKET)
    assert EXAMPLE_ROCKET == before


def test_c_w_zero_is_a_valid_step():
    # Gleiche Grenze wie RocketCreate: c_w >= 0
    configs = make(param_name="c_w", param_start=0.0, param_stop=1.0, n_steps=3).step_configs(EXAMPLE_ROCKET)
    assert [c.c_w for c in configs] == [0.0, 0.5, 1.0]


def test_invalid_step_raises_step_error_with_position():
    # v_bottle 1,5 l; der letzte Schritt (1,6 l Wasser) verletzt v_water0 < v_bottle
    s = make(param_name="v_water0", param_start=1e-4, param_stop=1.6e-3, n_steps=4)
    with pytest.raises(SeriesStepError) as info:
        s.step_configs(EXAMPLE_ROCKET)
    err = info.value
    assert err.step == 3
    assert err.param_name == "v_water0"
    assert err.value == 1.6e-3
    assert "v_water0 muss kleiner als v_bottle" in err.msg
    assert str(err).startswith("Schritt 3 (v_water0 = 0.0016)")


def test_step_error_is_a_value_error():
    assert issubclass(SeriesStepError, ValueError)


def test_first_invalid_step_is_reported():
    # Schritt 0 und 1 verletzen p0_gauge > 0; gemeldet wird Schritt 0
    s = make(param_start=-2.0, param_stop=1.0, n_steps=4)
    with pytest.raises(SeriesStepError) as info:
        s.step_configs(EXAMPLE_ROCKET)
    assert info.value.step == 0
    assert info.value.value == -2.0


def test_geometry_rules_apply_to_every_step():
    # Dünnerer Rumpf -> längere Wassersäule; bei d_body = 3 cm ist sie mit
    # 0,5 l Wasser länger als die Rakete (0,42 m). Die Regel stammt aus der
    # Physik und gilt nur mit Geometrie.
    s = make(param_name="d_body", param_start=0.03, param_stop=0.09, n_steps=3)
    with pytest.raises(SeriesStepError) as info:
        s.step_configs(replace(EXAMPLE_ROCKET, **GEOMETRY))
    assert info.value.step == 0
    assert "Wassersäule" in info.value.msg
    # Gegenprobe ohne Geometrie: dieselbe Serie ist gültig
    assert len(s.step_configs(EXAMPLE_ROCKET)) == 3


# --- Antwort -------------------------------------------------------------------

def test_series_read_from_row():
    row = Series(
        id=4, name="Druckserie", created_at=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        rocket_id=1, mode="forward", param_name="p0_gauge", param_start=2e5,
        param_stop=6e5, n_steps=5, searcher=None, duration_s=0.5,
    )
    data = SeriesRead.model_validate(row).model_dump()
    assert data["id"] == 4
    assert data["searcher"] is None
    assert data["duration_s"] == 0.5


def test_inverse_series_read_from_row():
    row = Series(
        id=5, name="Zielhoehen", created_at=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        rocket_id=1, mode="inverse", param_name="target_apogee", param_start=10.0,
        param_stop=40.0, n_steps=4, searcher="binary", duration_s=2.0,
    )
    data = SeriesRead.model_validate(row).model_dump()
    assert data["mode"] == "inverse"
    assert data["param_name"] == "target_apogee"
    assert data["searcher"] == "binary"