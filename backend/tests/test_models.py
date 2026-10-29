"""Tests für das Datenmodell (app/models.py).

Die Tabellen werden hier in einer SQLite-Datenbank im Arbeitsspeicher
angelegt. Das prüft die Python-Seite des Modells ohne laufende
PostgreSQL. Der Test gegen PostgreSQL folgt mit der Alembic-Migration.
"""

from dataclasses import fields, replace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    CONFIG_FIELDS, GEOMETRY_FIELDS, REQUIRED_CONFIG_FIELDS,
    Base, Flight, Rocket, Series, config_values,
)
from app.physics.simulation import EXAMPLE_ROCKET, FlightResult, RocketConfig

RESULT_FIELDS = [f.name for f in fields(FlightResult) if f.name != "trajectory"]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_config_fields_match_rocketconfig():
    assert list(CONFIG_FIELDS) == [f.name for f in fields(RocketConfig)]


def test_exactly_three_tables():
    assert set(Base.metadata.tables) == {"rockets", "series", "flights"}


@pytest.mark.parametrize("table", ["rockets", "flights"])
def test_config_columns_required(table):
    cols = Base.metadata.tables[table].columns
    for name in REQUIRED_CONFIG_FIELDS:
        assert name in cols
        assert cols[name].nullable is False


@pytest.mark.parametrize("table", ["rockets", "flights"])
def test_geometry_columns_optional(table):
    cols = Base.metadata.tables[table].columns
    for name in GEOMETRY_FIELDS:
        assert name in cols
        assert cols[name].nullable is True


def test_result_columns_match_flightresult():
    cols = Base.metadata.tables["flights"].columns
    for name in RESULT_FIELDS:
        assert name in cols
        assert cols[name].nullable is False
    assert "trajectory" not in cols


def test_series_id_optional_and_indexed():
    col = Base.metadata.tables["flights"].columns["series_id"]
    assert col.nullable is True
    assert col.index is True


def make_rocket():
    return Rocket(name="Beispiel", **config_values(EXAMPLE_ROCKET))


def make_flight(rocket, series=None):
    return Flight(
        rocket_id=rocket.id,
        series_id=series.id if series else None,
        model_version="test",
        **config_values(EXAMPLE_ROCKET),
        **{name: 1.0 for name in RESULT_FIELDS},
    )


def test_rocket_roundtrip(session):
    session.add(make_rocket())
    session.commit()
    rocket = session.query(Rocket).one()
    assert rocket.to_config() == EXAMPLE_ROCKET
    assert rocket.created_at is not None


def test_rocket_roundtrip_with_geometry(session):
    # Werte frei gewählt, NICHT gemessen.
    cfg = replace(
        EXAMPLE_ROCKET, nose_shape="ogive", l_nose=0.12, n_fins=4,
        fin_root_chord=0.10, fin_tip_chord=0.05, fin_span=0.08,
        fin_sweep=0.05, x_fin=0.30, x_cg_empty=0.25, l_total=0.42,
    )
    session.add(Rocket(name="Mit Finnen", **config_values(cfg)))
    session.commit()
    assert session.query(Rocket).one().to_config() == cfg


def test_flight_keeps_its_own_config(session):
    """Kassenbon: Der Flug behält seine Werte, auch wenn die Vorlage abweicht."""
    rocket = make_rocket()
    session.add(rocket)
    session.commit()
    flight = make_flight(rocket)
    flight.p0_gauge = 3e5  # z. B. ein Punkt einer Serie
    session.add(flight)
    session.commit()
    stored = session.query(Flight).one()
    assert stored.to_config().p0_gauge == 3e5
    assert session.query(Rocket).one().p0_gauge == EXAMPLE_ROCKET.p0_gauge
    assert stored.series_id is None


def test_series_with_flights(session):
    rocket = make_rocket()
    session.add(rocket)
    session.commit()
    series = Series(
        name="Druckstudie", rocket_id=rocket.id, mode="forward",
        param_name="p0_gauge", param_start=2e5, param_stop=7e5, n_steps=3,
    )
    session.add(series)
    session.commit()
    session.add_all([make_flight(rocket, series) for _ in range(3)])
    session.commit()
    rows = session.query(Flight).filter(Flight.series_id == series.id).all()
    assert len(rows) == 3


def test_missing_result_is_rejected(session):
    rocket = make_rocket()
    session.add(rocket)
    session.commit()
    flight = make_flight(rocket)
    flight.apogee = None
    session.add(flight)
    with pytest.raises(IntegrityError):
        session.commit()