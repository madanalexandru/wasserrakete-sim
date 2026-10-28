"""Phase 2 – Luftstoß: Restluft strömt nach dem Wasser durch die Düse.

Zustand y = [h, v, m_L] mit m_L = Luftmasse in der Flasche.
Flasche: Luft expandiert adiabatisch (p ~ rho^gamma, T ~ rho^(gamma-1)).
Düse: isentrope Gasströmung, zwei Fälle:
    p / p_atm >= 1,893  verblockt (Schall in der Düse), Druck an der Düse > p_atm
    p / p_atm <  1,893  unterkritisch, Druck an der Düse = p_atm
Schub F = mdot * u_e + (p_e - p_atm) * A_d

Vereinfachungen (Modellgrenzen): Luft als ideales Gas, Luftmasse in der
Raketenmasse vernachlässigt (konsistent zur Wasserphase), Ausflusskoeffizient = 1.
"""

import math
from dataclasses import dataclass

from app.physics.freeflight import G
from app.physics.integrator import rk4_step
from app.physics.waterphase import GAMMA, P_ATM, nozzle_area

R_AIR = 287.05  # spezifische Gaskonstante trockener Luft in J/(kg·K)
T_START = 293.15  # Starttemperatur der Luft in K (20 °C, Annahme)
CRITICAL_RATIO = ((GAMMA + 1) / 2) ** (GAMMA / (GAMMA - 1))  # ≈ 1,893


@dataclass
class AirPhaseResult:
    t_end: float  # Ende der Phase in s
    h_end: float  # Höhe am Ende in m
    v_end: float  # Geschwindigkeit am Ende in m/s
    p_end: float  # absoluter Luftdruck am Ende in Pa
    trajectory: list[tuple[float, float, float, float]]  # (t, h, v, m_L)


def temperature_after_expansion(t0: float, p: float, p0: float) -> float:
    """Temperatur nach adiabatischer Expansion von p0 auf p (in K)."""
    return t0 * (p / p0) ** ((GAMMA - 1) / GAMMA)


def nozzle_flow(p: float, temp: float, d_nozzle: float) -> tuple[float, float]:
    """Massenstrom (kg/s) und Schub (N) bei Flaschendruck p (Pa) und Temperatur temp (K)."""
    if p <= P_ATM:
        return 0.0, 0.0
    area = nozzle_area(d_nozzle)
    if p / P_ATM >= CRITICAL_RATIO:  # verblockt
        p_e = p / CRITICAL_RATIO
        t_e = 2 * temp / (GAMMA + 1)
        u_e = math.sqrt(GAMMA * R_AIR * t_e)
    else:  # unterkritisch
        p_e = P_ATM
        t_e = temp * (P_ATM / p) ** ((GAMMA - 1) / GAMMA)
        u_e = math.sqrt(2 * GAMMA / (GAMMA - 1) * R_AIR * (temp - t_e))
    mdot = p_e / (R_AIR * t_e) * area * u_e
    return mdot, mdot * u_e + (p_e - P_ATM) * area


def simulate_airphase(
    p_start: float,
    temp_start: float,
    v_bottle: float,
    d_nozzle: float,
    m_empty: float,
    k_drag: float,
    h0: float,
    v0: float,
    t0: float = 0.0,
    dt: float = 1e-5,
    max_steps: int = 10_000_000,
) -> AirPhaseResult:
    """Integriert den Luftstoß ab (h0, v0), bis der Flaschendruck p_atm erreicht."""
    if v_bottle <= 0 or d_nozzle <= 0 or m_empty <= 0 or dt <= 0 or k_drag < 0:
        raise ValueError("Volumen, Düse, Masse und dt müssen > 0 sein, k_drag >= 0.")
    if p_start <= P_ATM:  # kein Restdruck -> kein Luftstoß
        return AirPhaseResult(t0, h0, v0, p_start, [(t0, h0, v0, 0.0)])

    rho_start = p_start / (R_AIR * temp_start)

    def state(m_air: float) -> tuple[float, float]:
        ratio = max(m_air, 0.0) / v_bottle / rho_start
        return p_start * ratio**GAMMA, temp_start * ratio ** (GAMMA - 1)

    def derivatives(t: float, y: list[float]) -> list[float]:
        h, v, m_air = y
        mdot, force = nozzle_flow(*state(m_air), d_nozzle)
        return [v, (force - k_drag * v * abs(v)) / m_empty - G, -mdot]

    t, y = t0, [h0, v0, rho_start * v_bottle]
    trajectory = [(t, *y)]
    for _ in range(max_steps):
        y = rk4_step(derivatives, t, y, dt)
        t += dt
        trajectory.append((t, *y))
        p, _ = state(y[2])
        if p <= P_ATM:
            # Grobes Ende auf einen Zeitschritt genau (binäre Suche folgt später).
            return AirPhaseResult(t, y[0], y[1], p, trajectory)
    raise RuntimeError("Luftstoß nicht beendet: max_steps zu klein.")