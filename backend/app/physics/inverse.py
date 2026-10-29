"""Inverser Modus: Startdruck (Überdruck) für eine vorgegebene Zielhöhe.

Zielfunktion f(p) = Apogäum der Rakete mit Startdruck p (ein ganzer Flug).
Zulässig, weil das Apogäum monoton mit dem Startdruck steigt
(Sandbox-Prüfung Beispielrakete: 100 Stützstellen 0,1–10 bar, Feinscan um 5 bar).
Der Füllstand ist nicht monoton und wird hier bewusst NICHT gesucht.

Unter dem Abhebedruck ist das Apogäum ≈ 0 (teils −3e-8 m, kein Boden modelliert).
Für die Suche ist das unschädlich, solange target > 0: Alle diese Werte liegen
unter dem Ziel, die Suche geht dort immer nach rechts.
"""

import dataclasses
from dataclasses import dataclass

from app.physics.simulation import RocketConfig, simulate_flight
from app.search.exponential_search import ExponentialSearch
from app.search.searchable import Searchable

P_TOL = 1.0  # Pa; Begründung siehe projektlog.txt (Toleranz inverser Modus)
P_MIN = 1e3  # Pa; Suchuntergrenze (0 Pa ist in simulate_flight unzulässig)
P_MAX = 1e6  # Pa; Suchobergrenze = obere Grenze des geprüften Monotoniebereichs (10 bar).
#              KEINE Sicherheitsgrenze: Ein zulässiger Flaschendruck ist nicht
#              modelliert (keine belastbare Quelle gefunden, siehe Limitations).
STEP0 = 5e4  # Pa; erste Schrittweite der Exponentialsuche (0,5 bar), Annahme


@dataclass
class InverseResult:
    p0_gauge: float  # gefundener Startdruck (Überdruck) in Pa
    apogee: float  # Apogäum beim gefundenen Druck in m (Kontrollflug)
    target: float  # vorgegebene Zielhöhe in m
    search_evaluations: int  # Flüge während der Suche (Vergleichsmetrik)
    iterations: int  # Verdopplungen + Halbierungen
    width: float  # Breite des Restintervalls in Pa
    converged: bool


def find_start_pressure(
    cfg: RocketConfig,
    target: float,
    p_min: float = P_MIN,
    p_max: float = P_MAX,
    tol: float = P_TOL,
    searcher: Searchable | None = None,
) -> InverseResult:
    """Sucht den Überdruck p in [p_min, p_max], bei dem das Apogäum = target ist.

    Alle übrigen Parameter stammen aus cfg; cfg.p0_gauge wird ignoriert und
    nicht verändert. searcher ist austauschbar (Standard: Exponentialsuche).
    """
    if not target > 0:
        raise ValueError("Zielhöhe muss > 0 m sein.")
    if searcher is None:
        searcher = ExponentialSearch(step0=STEP0)

    def apogee_at(p: float) -> float:
        return simulate_flight(dataclasses.replace(cfg, p0_gauge=p)).apogee

    r = searcher.search(apogee_at, target, p_min, p_max, tol)
    return InverseResult(
        p0_gauge=r.x,
        apogee=apogee_at(r.x),  # Kontrollflug, zählt nicht zu search_evaluations
        target=target,
        search_evaluations=r.evaluations,
        iterations=r.iterations,
        width=r.width,
        converged=r.converged,
    )