"""Binäre Suche auf einem kontinuierlichen, monotonen Intervall.

Vorlage: Listing 7.8 (Pfob, „Fortgeschrittene Programmierung“, Abschnitt 7.4.2).
Anpassungen gegenüber dem Listing:
  1. float statt int: left/right werden auf mid gesetzt, nicht mid ± 1,
     weil zwischen zwei Gleitkommazahlen weitere Werte liegen.
  2. Abbruch, wenn das Intervall <= tol ist (statt left <= right).
  3. Zusätzlicher Abbruch, wenn mid nicht mehr zwischen lo und hi liegt
     (Maschinengenauigkeit erreicht) oder max_iter überschritten ist.
  4. Fallende Funktionen werden ebenfalls unterstützt (z. B. v(t) beim Apogäum).
  5. „return -1“ wird zu einem ValueError, wenn target nicht zwischen f(lo) und f(hi) liegt.
"""

from collections.abc import Callable

from app.search.searchable import Searchable, SearchResult


class BinarySearch(Searchable):
    def __init__(self, max_iter: int = 200):
        self.max_iter = max_iter

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

        f_lo, f_hi = f(lo), f(hi)
        evaluations = 2
        if f_lo == target:
            return SearchResult(lo, 0, evaluations, hi - lo, True)
        if f_hi == target:
            return SearchResult(hi, 0, evaluations, hi - lo, True)
        if not min(f_lo, f_hi) < target < max(f_lo, f_hi):
            raise ValueError("target liegt nicht zwischen f(lo) und f(hi).")
        increasing = f_hi > f_lo

        iterations = 0
        while hi - lo > tol and iterations < self.max_iter:
            mid = lo + (hi - lo) / 2  # wie Listing 7.8, Zeile 11
            if not lo < mid < hi:  # Maschinengenauigkeit erreicht
                break
            iterations += 1
            f_mid = f(mid)
            evaluations += 1
            if f_mid == target:  # exakter Treffer, wie Listing 7.8, Zeile 13
                return SearchResult(mid, iterations, evaluations, hi - lo, True)
            if (f_mid < target) == increasing:
                lo = mid  # Ziel liegt rechts
            else:
                hi = mid  # Ziel liegt links

        width = hi - lo
        return SearchResult(lo + width / 2, iterations, evaluations, width, width <= tol)