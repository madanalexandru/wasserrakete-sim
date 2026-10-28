"""Gesamtflug: Wasserschub -> Luftstoß -> Freiflug bis zum Apogäum.

Die Phasen werden nacheinander gerechnet; der Endzustand einer Phase
(t, h, v) ist der Startzustand der nächsten.
"""

from dataclasses import dataclass

from app.physics.airphase import T_START, simulate_airphase, temperature_after_expansion
from app.physics.freeflight import drag_factor, simulate_freeflight
from app.physics.waterphase import P_ATM, RHO_WATER, simulate_waterphase


@dataclass
class RocketConfig:
    v_bottle: float  # Flaschenvolumen in m³
    v_water0: float  # Wasservolumen beim Start in m³
    p0_gauge: float  # Startdruck als Überdruck in Pa
    d_nozzle: float  # Düsendurchmesser in m
    m_empty: float  # Leermasse der Rakete in kg
    c_w: float  # Luftwiderstandsbeiwert
    d_body: float  # Rumpfdurchmesser in m (für die Stirnfläche)
    temp0: float = T_START  # Lufttemperatur beim Start in K


# Beispielrakete: plausible Werte für eine 1,5-l-Flasche, NICHT gemessen.
# c_w = 0,5 ist ein Platzhalter bis zur Sensitivitätsanalyse (Phase 4).
EXAMPLE_ROCKET = RocketConfig(
    v_bottle=1.5e-3,
    v_water0=0.5e-3,
    p0_gauge=5e5,
    d_nozzle=0.022,
    m_empty=0.15,
    c_w=0.5,
    d_body=0.09,
)


@dataclass
class FlightResult:
    apogee: float  # m
    t_apogee: float  # s
    t_water_end: float  # Ende Wasserschub in s
    t_air_end: float  # Ende Luftstoß in s
    v_burnout: float  # Geschwindigkeit am Ende des Schubs in m/s
    h_burnout: float  # Höhe am Ende des Schubs in m
    water_rest: float  # nicht ausgestoßenes Wasser in m³
    trajectory: list[tuple[float, float, float]]  # (t, h, v)


def simulate_flight(cfg: RocketConfig) -> FlightResult:
    k = drag_factor(cfg.c_w, cfg.d_body)
    p0_abs = cfg.p0_gauge + P_ATM

    water = simulate_waterphase(
        cfg.v_bottle, cfg.v_water0, cfg.p0_gauge, cfg.d_nozzle, cfg.m_empty, k
    )
    temp = temperature_after_expansion(cfg.temp0, water.p_end, p0_abs)
    air = simulate_airphase(
        water.p_end, temp, cfg.v_bottle, cfg.d_nozzle, cfg.m_empty, k,
        h0=water.h_end, v0=water.v_end, t0=water.t_end,
    )
    trajectory = [(t, h, v) for t, h, v, _ in water.trajectory]
    trajectory += [(t, h, v) for t, h, v, _ in air.trajectory[1:]]

    # Bleibt Wasser übrig, fliegt es im Freiflug mit.
    m_free = cfg.m_empty + RHO_WATER * water.water_rest
    if air.v_end > 0:
        free = simulate_freeflight(air.h_end, air.v_end, m_free, k, t0=air.t_end)
        trajectory += free.trajectory[1:]
        apogee, t_apogee = free.apogee, free.t_apogee
    else:  # Rakete steigt nach dem Schub nicht mehr
        apogee, t_apogee = air.h_end, air.t_end

    return FlightResult(
        apogee, t_apogee, water.t_end, air.t_end,
        air.v_end, air.h_end, water.water_rest, trajectory,
    )