"""Tests für thin_trajectory (app/trajectory.py).

Geprüft wird: kurze Kurven bleiben unverändert; erster und letzter Punkt
bleiben exakt; höchstens max_points Punkte; nur vorhandene Punkte in der
ursprünglichen Reihenfolge (keine Interpolation); behaltene Punkte liegen
zeitlich gleichmäßig, auch wenn die Eingabe einen dichten Abschnitt hat
(wie die Schubphasen); ungültige Aufrufe -> ValueError.

Die Kurve der Beispielrakete wird nur auf Eigenschaften geprüft. Die
Fehlermeldungen nennen keine Höhen, damit kein Apogäum sichtbar wird.
"""

import pytest

from app.physics.simulation import EXAMPLE_ROCKET, simulate_flight
from app.trajectory import MAX_POINTS, thin_trajectory


def uniform(n: int, dt: float = 1.0) -> list[tuple[float, float, float]]:
    """n Punkte im Abstand dt; h und v frei gewählt."""
    return [(i * dt, float(i), -float(i)) for i in range(n)]


def dense_then_coarse() -> list[tuple[float, float, float]]:
    """Wie ein Flug: 5000 Punkte in 0,05 s, dann 1000 Punkte in 1 s."""
    dense = [(i * 1e-5, 0.0, 0.0) for i in range(5000)]
    coarse = [(0.05 + i * 1e-3, 1.0, 1.0) for i in range(1, 1001)]
    return dense + coarse


def is_subsequence(part, whole) -> bool:
    it = iter(whole)
    return all(any(p is q for q in it) for p in part)


def max_gap(points) -> float:
    return max(b[0] - a[0] for a, b in zip(points, points[1:]))


# --- Kurze Kurven ------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 10, MAX_POINTS])
def test_short_trajectory_unchanged(n):
    points = uniform(n)
    assert thin_trajectory(points) == points


def test_short_trajectory_is_a_copy():
    points = uniform(3)
    result = thin_trajectory(points)
    result.append((99.0, 0.0, 0.0))
    assert len(points) == 3


# --- Grundeigenschaften ------------------------------------------------------

@pytest.mark.parametrize("n, max_points", [(501, 500), (1001, 11), (10_000, 500), (6000, 2)])
def test_at_most_max_points(n, max_points):
    assert len(thin_trajectory(uniform(n), max_points)) <= max_points


def test_uniform_grid_reaches_max_points_exactly():
    # 0, 1, ..., 1000 mit 11 Punkten: Raster 100 -> 0, 100, ..., 1000
    result = thin_trajectory(uniform(1001), 11)
    assert [p[0] for p in result] == [100.0 * i for i in range(11)]


def test_first_and_last_point_kept_exactly():
    points = dense_then_coarse()
    result = thin_trajectory(points)
    assert result[0] is points[0]
    assert result[-1] is points[-1]


def test_only_original_points_in_order():
    points = dense_then_coarse()
    assert is_subsequence(thin_trajectory(points), points)


def test_two_points_only_first_and_last():
    points = uniform(100)
    assert thin_trajectory(points, 2) == [points[0], points[-1]]


# --- Zeitlich gleichmäßig -----------------------------------------------------

def test_dense_part_does_not_dominate():
    # Jeder n-te Punkt ließe 5/6 der Punkte im dichten Abschnitt (0,05 s).
    points = dense_then_coarse()
    result = thin_trajectory(points, 101)
    in_dense = sum(1 for p in result if p[0] < 0.05)
    assert in_dense <= 6  # 0,05 s / Raster 0,0105 s ≈ 5 Punkte


def test_gap_at_most_grid_step_plus_largest_input_step():
    points = dense_then_coarse()
    max_points = 101
    step = (points[-1][0] - points[0][0]) / (max_points - 1)
    result = thin_trajectory(points, max_points)
    assert max_gap(result) <= step + max_gap(points)


# --- Ungültige Aufrufe -------------------------------------------------------

@pytest.mark.parametrize("max_points", [1, 0, -5])
def test_max_points_below_two_rejected(max_points):
    with pytest.raises(ValueError, match="max_points"):
        thin_trajectory(uniform(10), max_points)


def test_time_not_increasing_rejected():
    points = [(0.0, 0.0, 0.0)] * 10
    with pytest.raises(ValueError, match="Zeit"):
        thin_trajectory(points, 5)


# --- Kurve der Beispielrakete (nur Eigenschaften) ----------------------------

@pytest.fixture(scope="module")
def flight():
    return simulate_flight(EXAMPLE_ROCKET)


def test_example_flight_is_thinned(flight):
    assert len(flight.trajectory) > MAX_POINTS  # sonst prüft der Test nichts
    assert len(thin_trajectory(flight.trajectory)) <= MAX_POINTS


def test_example_flight_ends_at_apogee(flight):
    last = thin_trajectory(flight.trajectory)[-1]
    same = last[1] == flight.apogee and last[0] == flight.t_apogee and last[2] == 0.0
    assert same, "letzter Punkt ist nicht das Apogäum"


def test_example_flight_time_strictly_increasing(flight):
    times = [p[0] for p in thin_trajectory(flight.trajectory)]
    assert all(a < b for a, b in zip(times, times[1:]))


def test_example_flight_gap_bounded(flight):
    points = flight.trajectory
    step = (points[-1][0] - points[0][0]) / (MAX_POINTS - 1)
    ok = max_gap(thin_trajectory(points)) <= step + max_gap(points)
    assert ok, "Lücke größer als Raster plus größter Zeitschritt"