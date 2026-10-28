"""Austauschbares Such-Interface für monotone Funktionen.

Abgeleitet aus der Signatur der Skript-Listings 7.7 bis 7.10
(Pfob, „Fortgeschrittene Programmierung“, Abschnitt 7.4):

    int search(int[] numbers, int target)

Das Skript verwendet das Interface Searchable, druckt es aber nicht ab.
Übertragung auf kontinuierliche, monotone Intervalle:

    int[] numbers (sortiert)  ->  f: monotone Funktion auf [lo, hi]
    Index i                   ->  Stelle x (float) im Intervall
    numbers[i] == target      ->  f(x) == target bzw. Intervall <= tol
    return -1                 ->  ValueError (target nicht eingeschlossen)
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class SearchResult:
    x: float  # gefundene Stelle mit f(x) ≈ target
    iterations: int  # Anzahl der Halbierungs- bzw. Schätzschritte
    evaluations: int  # Anzahl der Aufrufe von f (Vergleichsmetrik)
    width: float  # Breite des Restintervalls am Ende
    converged: bool  # True: width <= tol oder exakter Treffer


class Searchable(ABC):
    """Gemeinsame Schnittstelle aller Suchverfahren (binär, Interpolation, exponentiell)."""

    @abstractmethod
    def search(
        self,
        f: Callable[[float], float],
        target: float,
        lo: float,
        hi: float,
        tol: float,
    ) -> SearchResult:
        """Sucht x in [lo, hi] mit f(x) = target. f muss auf [lo, hi] monoton sein."""