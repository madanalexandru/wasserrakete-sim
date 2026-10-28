"""Phase 1 – Wasserschub: Druckluft presst Wasser durch die Düse.

Modell (1D, nach oben positiv), Zustand y = [h, v, V_w]:
    p     = p0 * (V_L0 / V_L)^gamma          adiabatische Expansion, V_L = V_B - V_w
    u     = sqrt(2 * (p - p_atm) / rho_w)     Bernoulli, Austrittsgeschwindigkeit
    F     = rho_w * A_d * u^2                 Schub (= 2 * A_d * (p - p_atm))
    dV_w/dt = -A_d * u
    dv/dt   = (F - k * v * |v|) / m - g       mit m = m_leer + rho_w * V_w
    dh/dt   = v

Vereinfachungen (Modellgrenzen): Strömung in der Flasche vernachlässigt,
Ausflusskoeffizient = 1, Luftmasse vernachlässigt, kein Startrohr.
"""

import math
from dataclasses import dataclass

from app.physics.freeflight import G
from app.physics.integrator import rk4_step

RHO_WATER = 1000.0  # Dichte von Wasser in kg/m³ (Näherung)
P_ATM = 101325.0  # Atmosphärendruck in Pa (Normatmosphäre)
GAMMA = 1.4  # Isentropenexponent von Luft


@dataclass
class WaterPhaseResult:
    t_end: float  # Ende der Phase in s
    h_end: float  # Höhe am Ende in m
    v_end: float  # Geschwindigkeit am Ende in m/s
    water_rest: float  # verbliebenes Wasser in m³ (0 = leer)
    p_end: float  # absoluter Luftdruck am Ende in Pa
    water_empty: bool  # True: Wasser leer; False: Druck vorher verbraucht
    trajectory: list[tuple[float, float, float, float]]  # (t, h, v, V_w)


def nozzle_area(d_nozzle: float) -> float:
    return math.pi * d_nozzle**2 / 4


def air_pressure(v_water: float, v_bottle: float, v_water0: float, p0_abs: float) -> float:
    """Absoluter Luftdruck nach adiabatischer Expansion."""
    return p0_abs * ((v_bottle - v_water0) / (v_bottle - v_water)) ** GAMMA


def exit_velocity(p_abs: float) -> float:
    """Bernoulli: Austrittsgeschwindigkeit des Wassers in m/s."""
    return math.sqrt(2 * max(p_abs - P_ATM, 0.0) / RHO_WATER)


def thrust(p_abs: float, d_nozzle: float) -> float:
    """Schub F = rho_w * A_d * u² in N."""
    return RHO_WATER * nozzle_area(d_nozzle) * exit_velocity(p_abs) ** 2


def simulate_waterphase(
    v_bottle: float,
    v_water0: float,
    p0_gauge: float,
    d_nozzle: float,
    m_empty: float,
    k_drag: float,
    dt: float = 1e-5,
    max_steps: int = 10_000_000,
) -> WaterPhaseResult:
    """Integriert die Wasserphase vom Start (h = 0, v = 0) bis Wasser oder Druck leer ist."""
    if not 0 < v_water0 < v_bottle:
        raise ValueError("Es muss gelten: 0 < Wasservolumen < Flaschenvolumen.")
    if p0_gauge <= 0 or d_nozzle <= 0 or m_empty <= 0 or dt <= 0 or k_drag < 0:
        raise ValueError("Druck, Düse, Masse und dt müssen > 0 sein, k_drag >= 0.")

    p0_abs = p0_gauge + P_ATM
    area = nozzle_area(d_nozzle)

    def derivatives(t: float, y: list[float]) -> list[float]:
        h, v, v_water = y
        p = air_pressure(v_water, v_bottle, v_water0, p0_abs)
        u = exit_velocity(p)
        mass = m_empty + RHO_WATER * max(v_water, 0.0)
        a = (RHO_WATER * area * u**2 - k_drag * v * abs(v)) / mass - G
        if h <= 0 and v <= 0 and a < 0:  # Rakete steht noch auf dem Boden
            return [0.0, 0.0, -area * u]
        return [v, a, -area * u]

    t, y = 0.0, [0.0, 0.0, v_water0]
    trajectory = [(t, *y)]
    for _ in range(max_steps):
        y = rk4_step(derivatives, t, y, dt)
        t += dt
        trajectory.append((t, *y))
        p = air_pressure(y[2], v_bottle, v_water0, p0_abs)
        if y[2] <= 0 or p <= P_ATM:
            # Grobes Ende auf einen Zeitschritt genau.
            # Präzisierung später mit binärer Suche (Checkliste Phase 2).
            water_rest = max(y[2], 0.0)
            return WaterPhaseResult(t, y[0], y[1], water_rest, p, water_rest == 0.0, trajectory)
    raise RuntimeError("Wasserphase nicht beendet: max_steps zu klein.")