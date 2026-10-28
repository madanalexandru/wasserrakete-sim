"""Phase 3 – Freiflug: kein Schub, nur Schwerkraft und Luftwiderstand.

Modell (1D, nach oben positiv):
    dh/dt = v
    dv/dt = -g - (k / m) * v * |v|      mit k = 0.5 * rho * c_w * A

Simuliert wird nur der Aufstieg bis zum Apogäum (Abstieg: Future Work).
Das Apogäum (v = 0) liegt zwischen zwei Zeitschritten; es wird dort mit
einem austauschbaren Suchverfahren (Standard: binäre Suche) eingegrenzt.
"""

import math
from dataclasses import dataclass

from app.physics.integrator import rk4_step
from app.search.binary_search import BinarySearch
from app.search.searchable import Searchable

G = 9.80665  # Normfallbeschleunigung in m/s²
RHO_AIR = 1.225  # Luftdichte in kg/m³ (Normatmosphäre, Meereshöhe, 15 °C)
T_TOL = 1e-12  # Zeittoleranz der Apogäum-Suche in s


@dataclass
class FreeFlightResult:
    apogee: float  # maximale Höhe in m
    t_apogee: float  # Zeitpunkt des Apogäums in s
    trajectory: list[tuple[float, float, float]]  # (t, h, v) je Schritt, letzter Punkt = Apogäum
    search_evaluations: int = 0  # Aufrufe der Zielfunktion bei der Suche (Vergleichsmetrik)


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
    searcher: Searchable | None = None,
    t_tol: float = T_TOL,
) -> FreeFlightResult:
    """Integriert den Freiflug von (h0, v0) bis zum Apogäum (v = 0)."""
    if v0 <= 0:
        raise ValueError("v0 muss > 0 sein (nur Aufstieg wird simuliert).")
    if mass <= 0 or dt <= 0 or k_drag < 0:
        raise ValueError("mass und dt müssen > 0 sein, k_drag >= 0.")
    searcher = searcher or BinarySearch()

    def derivatives(t: float, y: list[float]) -> list[float]:
        h, v = y
        return [v, -G - (k_drag / mass) * v * abs(v)]

    t, y = t0, [h0, v0]
    trajectory = [(t, h0, v0)]
    for _ in range(max_steps):
        y_new = rk4_step(derivatives, t, y, dt)
        if y_new[1] <= 0:
            # Apogäum liegt in [t, t + dt]. Gesucht: Teilschritt s mit v(t + s) = 0.
            # v(s) = ein RK4-Schritt der Länge s ab (t, y); fällt monoton in s.
            def velocity_after(s: float, t=t, y=y) -> float:
                return rk4_step(derivatives, t, y, s)[1]

            found = searcher.search(velocity_after, 0.0, 0.0, dt, t_tol)
            h_apogee = rk4_step(derivatives, t, y, found.x)[0]
            t_apogee = t + found.x
            trajectory.append((t_apogee, h_apogee, 0.0))
            return FreeFlightResult(h_apogee, t_apogee, trajectory, found.evaluations)
        t += dt
        y = y_new
        trajectory.append((t, y[0], y[1]))
    raise RuntimeError("Apogäum nicht erreicht: max_steps zu klein.")