"""Exponentialsuche auf einem kontinuierlichen, monoton steigenden Intervall.

Vorlage: Listing 7.10 (Pfob, „Fortgeschrittene Programmierung“, Abschnitt 7.4.4).
Ablauf wie im Listing:
  1. Eingrenzung: Schrittweite verdoppeln, solange f(x) <= target (Z. 11–14).
  2. Binäre Suche zwischen letztem und vorletztem Punkt (Z. 16–32).

Anpassungen gegenüber dem Listing:
  1. float statt int: x = lo + step0 * 2^k statt Index i = 2^k.
  2. Linke Grenze = letzter geprüfter Punkt statt i / 2. Im Listing liefert
     i / 2 bei i = 1 nur durch Ganzzahldivision den Index 0; kontinuierlich
     wäre lo + step0 / 2 ein ungeprüfter Punkt.
  3. Die zweite Phase ruft die getestete BinarySearch auf, statt die
     Zeilen 20–32 zu kopieren.
  4. Cache: Jede Stelle wird höchstens einmal ausgewertet. Wichtig, weil
     eine Auswertung im inversen Modus ein ganzer Flug ist.
     evaluations = Anzahl verschiedener Aufrufe von f.
  5. hi entspricht array.length (Obergrenze, Z. 12 und 17).
     „return -1“ wird zu einem ValueError, wenn f(hi) < target oder f(lo) > target.
  6. Nur steigende Funktionen (der inverse Modus braucht nur diese).

iterations = Verdopplungen + Halbierungen.
"""

import math
from collections.abc import Callable

from app.search.binary_search import BinarySearch
from app.search.searchable import Searchable, SearchResult

DEFAULT_STEPS = 1024  # ohne step0: step0 = (hi - lo) / 1024


class ExponentialSearch(Searchable):
    def __init__(self, step0: float | None = None, max_iter: int = 200):
        if step0 is not None and not (step0 > 0 and math.isfinite(step0)):
            raise ValueError("step0 muss > 0 und endlich sein.")
        self.step0 = step0
        self.max_iter = max_iter  # für die binäre Phase

    def search(
        self,
        f: Callable[[float], float],
        target: float,
        lo: float,
        hi: float,
        tol: float,
    ) -> SearchResult:
        if not lo < hi:
            raise ValueError("Es muss gelten: lo < hi.")
        if tol <= 0:
            raise ValueError("tol muss > 0 sein.")

        cache: dict[float, float] = {}

        def g(x: float) -> float:
            if x not in cache:
                cache[x] = f(x)
            return cache[x]

        # Listing Z. 7–9: Treffer am Anfang
        f_lo = g(lo)
        if f_lo == target:
            return SearchResult(lo, 0, len(cache), 0.0, True)
        if f_lo > target:
            raise ValueError("target liegt unter f(lo).")

        # Listing Z. 11–14: Eingrenzung durch Verdopplung
        step = self.step0 if self.step0 is not None else (hi - lo) / DEFAULT_STEPS
        prev = lo  # letzter Punkt mit f <= target (Anpassung 2)
        doublings = 0
        while True:
            x = min(lo + step, hi)  # Listing Z. 17: Math.min(i, length - 1)
            doublings += 1
            f_x = g(x)
            if f_x > target:
                break
            if x >= hi:
                if f_x == target:
                    return SearchResult(hi, doublings, len(cache), 0.0, True)
                raise ValueError("target ist bis hi nicht erreichbar.")
            prev = x
            step *= 2

        # Listing Z. 16–32: binäre Suche in [prev, x], f(prev) <= target < f(x)
        inner = BinarySearch(max_iter=self.max_iter).search(g, target, prev, x, tol)
        return SearchResult(
            inner.x,
            doublings + inner.iterations,
            len(cache),
            inner.width,
            inner.converged,
        )