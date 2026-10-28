"""Tests für Phase 1 (Wasserschub)."""

import math

import pytest

from app.physics.freeflight import G, drag_factor
from app.physics.waterphase import (
    P_ATM,
    RHO_WATER,
    nozzle_area,
    simulate_waterphase,
    thrust,
)
from app.search.binary_search import BinarySearch

# Beispielrakete für Tests, keine Messwerte
V_BOTTLE = 1.5e-3  # m³ (1,5 l)
D_NOZZLE = 0.022  # m
M_EMPTY = 0.15  # kg
K_DRAG = drag_factor(c_w=0.5, diameter=0.09)


def test_schub_gleich_zwei_mal_flaeche_mal_ueberdruck():
    # Bernoulli + Impulssatz: rho * A * u² = 2 * A * (p - p_atm)
    p_abs = P_ATM + 5e5
    assert thrust(p_abs, D_NOZZLE) == pytest.approx(2 * nozzle_area(D_NOZZLE) * 5e5)


def rocket_equation(v_water0: float, p_gauge: float) -> tuple[float, float, float]:
    """Brenndauer, Endgeschwindigkeit und Endhöhe bei konstantem Druck.

    Raketengleichung mit Schwerkraft (ohne Luftwiderstand):
      v(t) = u * ln(m0 / m(t)) - g * t
      h(t) = u * (t + m(t)/mdot * ln(m(t)/m0)) - g * t² / 2
    """
    u = math.sqrt(2 * p_gauge / RHO_WATER)
    mdot = RHO_WATER * nozzle_area(D_NOZZLE) * u
    m0 = M_EMPTY + RHO_WATER * v_water0
    t_b = RHO_WATER * v_water0 / mdot
    v_exp = u * math.log(m0 / M_EMPTY) - G * t_b
    h_exp = u * (t_b + M_EMPTY / mdot * math.log(M_EMPTY / m0)) - G * t_b**2 / 2
    return t_b, v_exp, h_exp


def test_konstanter_druck_wie_raketengleichung():
    # Grenzfall: riesiges Luftvolumen -> Druck praktisch konstant.
    v_water0, p_gauge = 0.5e-3, 5e5
    t_b, v_exp, h_exp = rocket_equation(v_water0, p_gauge)
    r = simulate_waterphase(1e3, v_water0, p_gauge, D_NOZZLE, M_EMPTY, k_drag=0.0)
    assert r.water_empty
    assert r.t_end == pytest.approx(t_b, rel=1e-3)
    assert r.v_end == pytest.approx(v_exp, rel=1e-3)
    assert r.h_end == pytest.approx(h_exp, rel=1e-3)


def test_beispielrakete_wasser_wird_leer_und_druck_sinkt():
    r = simulate_waterphase(V_BOTTLE, 0.5e-3, 5e5, D_NOZZLE, M_EMPTY, K_DRAG)
    assert r.water_empty
    assert r.water_rest == 0.0
    assert P_ATM < r.p_end < P_ATM + 5e5
    assert r.v_end > 0 and r.h_end > 0


def test_masse_nimmt_monoton_ab():
    r = simulate_waterphase(V_BOTTLE, 0.5e-3, 5e5, D_NOZZLE, M_EMPTY, K_DRAG)
    volumes = [point[3] for point in r.trajectory]
    assert all(a > b for a, b in zip(volumes, volumes[1:]))


def test_zu_viel_wasser_druck_geht_zuerst_aus():
    # 1,4 l Wasser bei 1 bar: Der Druck fällt auf p_atm, bevor das Wasser leer ist.
    r = simulate_waterphase(V_BOTTLE, 1.4e-3, 1e5, D_NOZZLE, M_EMPTY, K_DRAG)
    assert not r.water_empty
    assert r.water_rest > 0
    assert r.p_end <= P_ATM


@pytest.mark.parametrize("v_water0", [0.0, 1.5e-3, 2e-3])
def test_ungueltiges_wasservolumen_wird_abgelehnt(v_water0):
    with pytest.raises(ValueError):
        simulate_waterphase(V_BOTTLE, v_water0, 5e5, D_NOZZLE, M_EMPTY, K_DRAG)


# --- Binäre Suche: Wasser-Ende genauer als ein Zeitschritt (dt = 1e-5 s) ---

def test_raketengleichung_mit_suche_viel_genauer():
    # Ohne Suche lag die rel. Abweichung bei ca. 1e-4 (t) bzw. 3e-4 (v, h).
    v_water0, p_gauge = 0.5e-3, 5e5
    t_b, v_exp, h_exp = rocket_equation(v_water0, p_gauge)
    r = simulate_waterphase(1e3, v_water0, p_gauge, D_NOZZLE, M_EMPTY, k_drag=0.0)
    assert r.t_end == pytest.approx(t_b, rel=1e-6)
    assert r.v_end == pytest.approx(v_exp, rel=1e-6)
    assert r.h_end == pytest.approx(h_exp, rel=1e-6)


def test_letzter_bahnpunkt_ist_phasenende():
    r = simulate_waterphase(V_BOTTLE, 0.5e-3, 5e5, D_NOZZLE, M_EMPTY, K_DRAG)
    t, h, v, v_water = r.trajectory[-1]
    assert (t, h, v, v_water) == (r.t_end, r.h_end, r.v_end, 0.0)
    times = [p[0] for p in r.trajectory]
    assert times == sorted(times)


def test_druckende_liegt_genau_bei_p_atm():
    r = simulate_waterphase(V_BOTTLE, 1.4e-3, 1e5, D_NOZZLE, M_EMPTY, K_DRAG)
    assert r.p_end == P_ATM
    assert r.trajectory[-1][3] == r.water_rest > 0


def test_suchaufwand_wird_gemeldet():
    # dt / tol = 1e-5 / 1e-12 -> ceil(log2(1e7)) = 24 Halbierungen + 2 Randwerte
    r = simulate_waterphase(V_BOTTLE, 0.5e-3, 5e5, D_NOZZLE, M_EMPTY, K_DRAG)
    assert 2 < r.search_evaluations <= 26


def test_suchverfahren_ist_austauschbar():
    class CountingSearch(BinarySearch):
        calls = 0

        def search(self, f, target, lo, hi, tol):
            CountingSearch.calls += 1
            return super().search(f, target, lo, hi, tol)

    simulate_waterphase(
        V_BOTTLE, 0.5e-3, 5e5, D_NOZZLE, M_EMPTY, K_DRAG, searcher=CountingSearch()
    )
    assert CountingSearch.calls == 1