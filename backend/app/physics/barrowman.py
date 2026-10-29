"""Druckpunkt nach Barrowman (1967), Unterschall.

Nur eine Stabilitätsprüfung: Die Flugphysik nutzt dieses Modul nicht.
Quelle: Barrowman, J. S. (1967), Kap. 3. Seiten = gedruckte Seitenzahlen
(PDF-Seite = gedruckte Seite + 10). Alle Längen in m ab Nasenspitze.

Bewusste Abweichungen von Barrowman (im Bericht begründet):
- Interferenzfaktor K_T(B) = 1 statt Gl. 3-96 (S. 31). Gedruckt liefert
  Gl. 3-96 ohne Rumpf (tau -> unendlich) den Wert 0,5 statt 1.
- Rumpf unter Finneneinfluss (Gl. 3-98, S. 31) vernachlässigt: Druckpunkt
  im Unterschall nur als Kurven (Abb. 3-10, S. 34-36).
- Ogivenvolumen numerisch statt Gl. 3-90 (S. 30). Gedruckt liefert
  Gl. 3-90 genau ein Viertel des integrierten Volumens.

Annahmen:
- beta = 1 (inkompressibel; Wasserrakete etwa Mach 0,13).
- Seitenverhältnis AR = 2 s² / A_f (zwei Finnen als ein Flügel); im
  Original keine Formel gefunden [QUELLE PRÜFEN].
- Nasendurchmesser = Rumpfdurchmesser (kein Übergang), spitze Nase (S. 2).
"""

from dataclasses import dataclass
from math import pi, sqrt

NOSE_SHAPES = ("cone", "ogive")
BETA = 1.0  # Annahme, siehe oben
N_SLICES = 2000  # Simpson-Abschnitte für das Ogivenvolumen (gerade Zahl)


@dataclass
class CenterOfPressure:
    x_cp: float  # Druckpunkt der ganzen Rakete in m ab Nasenspitze
    cn_alpha: float  # Normalkraftbeiwert-Ableitung gesamt in 1/rad
    x_nose: float
    cn_nose: float
    x_fins: float
    cn_fins: float


def volume_of_revolution(radius, length: float, n: int = N_SLICES) -> float:
    """Volumen eines Drehkörpers, pi * Integral r(x)² dx (Simpson-Regel)."""
    h = length / n
    total = radius(0.0) ** 2 + radius(length) ** 2
    for i in range(1, n):
        total += (4 if i % 2 else 2) * radius(i * h) ** 2
    return pi * total * h / 3


def ogive_radius(l_nose: float, d: float):
    """Radius r(x) einer Tangentenogive: Kreisbogen, tangential am Rumpf."""
    r = d / 2
    rho = (r * r + l_nose * l_nose) / (2 * r)  # Radius des Kreisbogens

    def radius(x: float) -> float:
        return sqrt(max(rho * rho - (l_nose - x) ** 2, 0.0)) + r - rho

    return radius


def nose_cp(shape: str, l_nose: float, d: float) -> float:
    """Druckpunkt der Nase, X = l - V/A (Gl. 3-89, S. 29)."""
    area = pi * d * d / 4
    if shape == "cone":
        volume = area * l_nose / 3
    else:
        volume = volume_of_revolution(ogive_radius(l_nose, d), l_nose)
    return l_nose - volume / area


def nose_cn_alpha() -> float:
    """(C_N_alpha)_B = 2 A_BN / A_r (Gl. 3-66, S. 21) mit A_BN = A_r."""
    return 2.0


def fins_cn_alpha(n: int, c_r: float, c_t: float, s: float, x_t: float, d: float) -> float:
    """Normalkraft des Finnensatzes im Unterschall (Gl. 3-12, S. 6)."""
    a_f = 0.5 * (c_r + c_t) * s  # Fläche einer Finne (Gl. 3-23, S. 9)
    a_r = pi * d * d / 4  # Bezugsfläche = Rumpfquerschnitt
    ar = 2 * s * s / a_f  # Annahme, siehe oben
    # Pfeilung der Mittellinie aus Abb. 3-2 (S. 7), eigene Herleitung
    tan_gc = (x_t + c_t / 2 - c_r / 2) / s
    cos_gc = 1 / sqrt(1 + tan_gc * tan_gc)
    return n * pi * ar * (a_f / a_r) / (2 + sqrt(4 + (BETA * ar / cos_gc) ** 2))


def fins_cp(x_fin: float, c_r: float, c_t: float, x_t: float) -> float:
    """Druckpunkt der Finnen (Gl. 3-30, S. 10)."""
    return (
        x_fin
        + x_t / 3 * (c_r + 2 * c_t) / (c_r + c_t)
        + (c_r + c_t - c_r * c_t / (c_r + c_t)) / 6
    )


REQUIRED = ("nose_shape", "l_nose", "n_fins", "fin_root_chord",
            "fin_tip_chord", "fin_span", "fin_sweep", "x_fin")


def check_geometry(cfg) -> None:
    """ValueError mit Feldnamen, wenn Geometrie fehlt oder unzulässig ist."""
    missing = [name for name in REQUIRED if getattr(cfg, name) is None]
    if missing:
        raise ValueError(f"Geometrie fehlt: {', '.join(missing)}")
    if cfg.nose_shape not in NOSE_SHAPES:
        raise ValueError(f"nose_shape muss {NOSE_SHAPES} sein")
    if cfg.n_fins not in (3, 4):
        raise ValueError("n_fins muss 3 oder 4 sein (Barrowman, S. 1)")
    for name in ("l_nose", "fin_root_chord", "fin_span", "d_body"):
        if getattr(cfg, name) <= 0:
            raise ValueError(f"{name} muss > 0 sein")
    if cfg.fin_tip_chord < 0 or cfg.x_fin < 0:
        raise ValueError("fin_tip_chord und x_fin dürfen nicht negativ sein")


def center_of_pressure(cfg) -> CenterOfPressure:
    """Gesamtdruckpunkt als gewichtetes Mittel (Gl. 3-106/3-107, S. 37)."""
    check_geometry(cfg)
    x_n = nose_cp(cfg.nose_shape, cfg.l_nose, cfg.d_body)
    cn_n = nose_cn_alpha()
    x_f = fins_cp(cfg.x_fin, cfg.fin_root_chord, cfg.fin_tip_chord, cfg.fin_sweep)
    cn_f = fins_cn_alpha(cfg.n_fins, cfg.fin_root_chord, cfg.fin_tip_chord,
                         cfg.fin_span, cfg.fin_sweep, cfg.d_body)  # K_T(B) = 1
    cn = cn_n + cn_f
    return CenterOfPressure((x_n * cn_n + x_f * cn_f) / cn, cn, x_n, cn_n, x_f, cn_f)