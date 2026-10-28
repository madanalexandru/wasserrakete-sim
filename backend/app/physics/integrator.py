"""Numerischer Integrator: klassisches Runge-Kutta-Verfahren 4. Ordnung (RK4).

Wird von allen Flugphasen genutzt. Der Zustand y ist eine Liste von Zahlen,
z. B. [Höhe, Geschwindigkeit]. f(t, y) liefert die Ableitungen dy/dt.
"""

from collections.abc import Callable, Sequence

Derivative = Callable[[float, Sequence[float]], list[float]]


def rk4_step(f: Derivative, t: float, y: Sequence[float], dt: float) -> list[float]:
    """Berechnet den Zustand nach einem Zeitschritt dt."""
    k1 = f(t, y)
    k2 = f(t + dt / 2, [yi + dt / 2 * ki for yi, ki in zip(y, k1)])
    k3 = f(t + dt / 2, [yi + dt / 2 * ki for yi, ki in zip(y, k2)])
    k4 = f(t + dt, [yi + dt * ki for yi, ki in zip(y, k3)])
    return [
        yi + dt / 6 * (a + 2 * b + 2 * c + d)
        for yi, a, b, c, d in zip(y, k1, k2, k3, k4)
    ]