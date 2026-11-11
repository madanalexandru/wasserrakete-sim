"""Vorhersage des Suchaufwands im inversen Modus (Auswertungen von f).

Binäre Suche und Exponentialsuche vergleichen nur, ob f(x) unter oder über
dem Ziel liegt. Bei monotonem f hängt ihr Suchweg daher nur von der Lage
der Lösung p* ab, nicht von der Form der Kurve. Diese Tests prüfen die
vorab festgelegte Tabelle mit den Suchverfahren und Grenzen des inversen
Modus (wie in der API), mit f(p) = p und einer gekrümmten Kurve.

Grenzen: Stellen, an denen die Exponentialsuche vor der Halbierung
auswertet, sowie P_MIN und P_MAX. Punkte näher als 1 Pa an einer Grenze
werden nicht geprüft, weil dort die Toleranz die Seite bestimmt.
"""

import pytest

from app.main import SEARCHER_FACTORIES
from app.physics.inverse import P_MAX, P_MIN, P_TOL, STEP0

# Vorhergesagte Auswertungen der Exponentialsuche je Band (Pa, Überdruck)
H2_BANDS = [
    (1e3, 51e3, 18),
    (51e3, 101e3, 19),
    (101e3, 201e3, 21),
    (201e3, 401e3, 23),
    (401e3, 1e6, 25),
]
H1_BINARY = 22
GRENZEN = [1e3, 51e3, 101e3, 201e3, 401e3, 801e3, 1e6]
MIN_ABSTAND = 1.0  # Pa


def h2_expected(p):
    for lo, hi, n in H2_BANDS:
        if lo < p < hi:
            return n
    raise ValueError(p)


def test_parameter_wie_in_der_vorab_notiz():
    assert (P_MIN, P_MAX, P_TOL, STEP0) == (1e3, 1e6, 1.0, 5e4)


def test_grenzen_sind_die_pruefstellen_der_exponentialsuche():
    calls = []

    def f(p):
        calls.append(p)
        return p

    SEARCHER_FACTORIES["exponential"]().search(f, 999_000.37, P_MIN, P_MAX, P_TOL)
    assert calls[: len(GRENZEN)] == GRENZEN


def punkte():
    """Viele Lösungen p* über den ganzen Bereich, mindestens 1 Pa von jeder Grenze."""
    result = []
    for i in range(2000):
        p = P_MIN + (P_MAX - P_MIN) * (i + 0.5) / 2000 + 0.37
        if all(abs(p - g) >= MIN_ABSTAND for g in GRENZEN):
            result.append(p)
    for g in GRENZEN:  # knapp neben jeder Grenze, auf beiden Seiten
        for d in (-1.37, 1.37):
            if P_MIN < g + d < P_MAX:
                result.append(g + d)
    return result


PUNKTE = punkte()


def kurven(p_star):
    """(f, Ziel) mit Lösung p*: Gerade und gekrümmte, steigende Kurve."""
    return [
        (lambda p: p, p_star),
        (lambda p: (p / 1e3) ** 0.5, (p_star / 1e3) ** 0.5),
    ]


def test_genug_punkte_in_jedem_band():
    for lo, hi, _ in H2_BANDS:
        assert sum(1 for p in PUNKTE if lo < p < hi) >= 50


@pytest.mark.parametrize("kurve", [0, 1], ids=["gerade", "gekruemmt"])
def test_h2_exponentialsuche_nach_tabelle(kurve):
    abweichend = []
    for p_star in PUNKTE:
        f, target = kurven(p_star)[kurve]
        r = SEARCHER_FACTORIES["exponential"]().search(f, target, P_MIN, P_MAX, P_TOL)
        assert r.converged
        if r.evaluations != h2_expected(p_star):
            abweichend.append((p_star, r.evaluations))
    assert abweichend == []


@pytest.mark.parametrize("kurve", [0, 1], ids=["gerade", "gekruemmt"])
def test_h1_binaere_suche_immer_22(kurve):
    abweichend = []
    for p_star in PUNKTE:
        f, target = kurven(p_star)[kurve]
        r = SEARCHER_FACTORIES["binary"]().search(f, target, P_MIN, P_MAX, P_TOL)
        assert r.converged
        if r.evaluations != H1_BINARY:
            abweichend.append((p_star, r.evaluations))
    assert abweichend == []


def test_exponentialsuche_ueber_201_kpa_teurer_als_binaer():
    # Folge aus H1 und H2, wie in der Vorab-Notiz formuliert
    for lo, hi, n in H2_BANDS:
        if lo >= 201e3:
            assert n > H1_BINARY
        else:
            assert n < H1_BINARY