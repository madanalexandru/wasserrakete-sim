"""Tests für Phase 3 (Freiflug) gegen analytische Lösungen."""

import math

import pytest

from app.physics.freeflight import G, drag_factor, simulate_freeflight

# Beispielwerte für Tests, keine Messwerte
MASS = 0.15  # kg
DIAMETER = 0.09  # m


def t_apogee_with_drag(v0: float, k: float, m: float = MASS) -> float:
    """Analytische Steigzeit mit quadratischem Luftwiderstand."""
    return math.sqrt(m / (G * k)) * math.atan(v0 * math.sqrt(k / (m * G)))


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


# --- Binäre Suche: Apogäum genauer als ein Zeitschritt (dt = 1e-3 s) ---

@pytest.mark.parametrize("h0, v0", [(0.0, 10.0), (0.0, 30.0), (5.0, 50.0)])
def test_apogaeumszeit_ohne_luftwiderstand_viel_genauer_als_dt(h0, v0):
    result = simulate_freeflight(h0=h0, v0=v0, mass=MASS, k_drag=0.0)
    assert result.t_apogee == pytest.approx(v0 / G, abs=1e-9)
    assert result.apogee == pytest.approx(h0 + v0**2 / (2 * G), abs=1e-9)


def test_apogaeumszeit_mit_luftwiderstand_viel_genauer_als_dt():
    v0 = 30.0
    k = drag_factor(c_w=0.5, diameter=DIAMETER)
    result = simulate_freeflight(h0=0.0, v0=v0, mass=MASS, k_drag=k)
    assert result.t_apogee == pytest.approx(t_apogee_with_drag(v0, k), abs=1e-9)


def test_letzter_bahnpunkt_ist_apogaeum():
    result = simulate_freeflight(h0=0.0, v0=30.0, mass=MASS, k_drag=0.0)
    t, h, v = result.trajectory[-1]
    assert (t, h, v) == (result.t_apogee, result.apogee, 0.0)
    times = [p[0] for p in result.trajectory]
    assert times == sorted(times)


def test_suchaufwand_wird_gemeldet():
    # dt / tol = 1e-3 / 1e-12 -> ceil(log2(1e9)) = 30 Halbierungen + 2 Randwerte
    result = simulate_freeflight(h0=0.0, v0=30.0, mass=MASS, k_drag=0.0)
    assert result.search_evaluations == 32