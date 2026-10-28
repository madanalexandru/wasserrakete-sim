"""Phase 3 – Freiflug: kein Schub, nur Schwerkraft und Luftwiderstand.

Modell (1D, nach oben positiv):
    dh/dt = v
    dv/dt = -g - (k / m) * v * |v|      mit k = 0.5 * rho * c_w * A

Simuliert wird nur der Aufstieg bis zum Apogäum (Abstieg: Future Work).
"""

import math
from dataclasses import dataclass

from app.physics.integrator import rk4_step

G = 9.80665  # Normfallbeschleunigung in m/s²
RHO_AIR = 1.225  # Luftdichte in kg/m³ (Normatmosphäre, Meereshöhe, 15 °C)


@dataclass
class FreeFlightResult:
    apogee: float  # maximale Höhe in m
    t_apogee: float  # Zeitpunkt des Apogäums in s
    trajectory: list[tuple[float, float, float]]  # (t, h, v) je Schritt


def drag_factor(c_w: float, diameter: float, rho: float = RHO_AIR) -> float:
    """k = 0.5 * rho * c_w * A, mit A = Stirnfläche der Flasche."""
    area = math.pi * diameter**2 / 4
    return 0.5 * rho * c_w * area


def simulate_freeflight(
    h0: float,
    v0: float,
    mass: float,
    k_drag: float,
    dt: float = 1e-3,
    t0: float = 0.0,
    max_steps: int = 1_000_000,
) -> FreeFlightResult:
    """Integriert den Freiflug von (h0, v0) bis die Geschwindigkeit <= 0 ist."""
    if v0 <= 0:
        raise ValueError("v0 muss > 0 sein (nur Aufstieg wird simuliert).")
    if mass <= 0 or dt <= 0 or k_drag < 0:
        raise ValueError("mass und dt müssen > 0 sein, k_drag >= 0.")

    def derivatives(t: float, y: list[float]) -> list[float]:
        h, v = y
        return [v, -G - (k_drag / mass) * v * abs(v)]

    t, y = t0, [h0, v0]
    trajectory = [(t, h0, v0)]
    for _ in range(max_steps):
        y_new = rk4_step(derivatives, t, y, dt)
        t += dt
        trajectory.append((t, y_new[0], y_new[1]))
        if y_new[1] <= 0:
            # Das Apogäum liegt zwischen den letzten beiden Schritten.
            # Vorläufig: den höheren Punkt nehmen (Fehler <= g*dt²/8).
            # Präzisierung später mit binärer Suche (Checkliste Phase 2).
            if y_new[0] >= y[0]:
                return FreeFlightResult(y_new[0], t, trajectory)
            return FreeFlightResult(y[0], t - dt, trajectory)
        y = y_new
    raise RuntimeError("Apogäum nicht erreicht: max_steps zu klein.")