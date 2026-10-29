"""Interpolationssuche auf einem kontinuierlichen, monotonen Intervall.

Vorlage: Listing 7.9 (Pfob, „Fortgeschrittene Programmierung“, Abschnitt 7.4.3).
Idee wie im Listing: Statt der Mitte wird die Stelle geschätzt, an der eine
Gerade durch die beiden Randpunkte den Zielwert erreicht (Listing Z. 11).

Behobene Fehler des Listings:
  1. Z. 11 teilt (high - low) / (numbers[high] - numbers[low]) als Ganzzahl
     VOR der Multiplikation. Ist der Wertebereich größer als der Indexbereich,
     ergibt das 0, pos = low und die Suche wird linear.
     Hier: erst multiplizieren, dann teilen (Gleitkomma).
  2. Z. 11 teilt durch null, wenn numbers[high] == numbers[low]
     (z. B. bei einem Array mit nur einem Element).
     Hier: Gleiche Randwerte werden vor der Schleife abgefangen (Treffer oder
     ValueError). In der Schleife kann der Nenner nicht 0 werden, weil die
     Abstände d_lo und d_hi zum Ziel immer verschiedene Vorzeichen haben.

Anpassungen für kontinuierliche Intervalle (wie bei BinarySearch):
  3. lo/hi werden auf die Schätzstelle gesetzt, nicht pos ± 1.
  4. Abbruch, wenn das Intervall <= tol ist (gleiche Toleranz wie die
     anderen Verfahren), oder bei max_iter.
  5. Fällt die Schätzung durch Rundung auf lo oder hi, wird die Mitte genommen;
     ist auch das nicht möglich, ist die Maschinengenauigkeit erreicht.
  6. Steigende und fallende Funktionen; „return -1“ wird zu ValueError.

Zusatzregel (Illinois-Verfahren):
  7. Kontinuierlich entspricht die Interpolationssuche der Regula falsi. Ist
     die Funktion im Intervall konvex oder konkav, bleibt eine Grenze stehen
     (Dowell & Jarratt 1971, S. 168), und das Intervall wird nie <= tol.
     Darum: Rückt dieselbe Grenze zweimal hintereinander, wird der
     gespeicherte Abstand der stehenden Grenze zum Ziel halbiert (Regel ii,
     ebd., S. 169). Die nächste Schätzung landet dann meist auf der anderen
     Seite, und die stehende Grenze rückt nach.
     Quelle: M. Dowell, P. Jarratt: A modified regula falsi method for
     computing the root of an equation. BIT 11 (1971), 168-174.
     Das Verfahren selbst stammt laut ebd. (S. 169) vermutlich vom
     Rechenzentrum der University of Illinois (frühe 1950er Jahre).
     Mit illinois=False wird das Stehenbleiben für den Vergleich sichtbar.
"""

from collections.abc import Callable

from app.search.searchable import Searchable, SearchResult


class InterpolationSearch(Searchable):
    def __init__(self, max_iter: int = 200, illinois: bool = True):
        self.max_iter = max_iter
        self.illinois = illinois

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
        # Fix 2: Ab hier gilt f(lo) != f(hi), sonst wäre target nicht dazwischen
        if not min(f_lo, f_hi) < target < max(f_lo, f_hi):
            raise ValueError("target liegt nicht zwischen f(lo) und f(hi).")
        increasing = f_hi > f_lo

        # Abstand der Randwerte zum Ziel (haben immer verschiedene Vorzeichen)
        d_lo, d_hi = f_lo - target, f_hi - target
        last_moved = None  # welche Grenze zuletzt gerückt ist ("lo" oder "hi")

        iterations = 0
        while hi - lo > tol and iterations < self.max_iter:
            # Listing Z. 11 mit Fix 1: erst multiplizieren, dann teilen.
            # Nenner != 0 (Fix 2), weil d_lo und d_hi verschiedene Vorzeichen haben.
            x = lo + ((hi - lo) * d_lo) / (d_lo - d_hi)
            if not lo < x < hi:  # Anpassung 5: Schätzung liegt auf dem Rand
                x = lo + (hi - lo) / 2
                if not lo < x < hi:  # Maschinengenauigkeit erreicht
                    break
            iterations += 1
            f_x = f(x)
            evaluations += 1
            if f_x == target:  # exakter Treffer, wie Listing 7.9, Zeile 13
                return SearchResult(x, iterations, evaluations, hi - lo, True)
            if (f_x < target) == increasing:
                lo, d_lo, moved = x, f_x - target, "lo"  # Ziel liegt rechts
            else:
                hi, d_hi, moved = x, f_x - target, "hi"  # Ziel liegt links

            if self.illinois and moved == last_moved:  # Zusatzregel 7
                if moved == "lo":
                    d_hi /= 2  # hi ist stehen geblieben
                else:
                    d_lo /= 2  # lo ist stehen geblieben
            last_moved = moved

        width = hi - lo
        return SearchResult(lo + width / 2, iterations, evaluations, width, width <= tol)