"""Stabilitätsprüfung: Druckpunkt (Barrowman) gegen Schwerpunkt.

Nur eine Prüfung, nicht Teil der Flugphysik.
Stabilitätsmaß in Kalibern: (x_CP - x_CG) / d_body, Längen ab Nasenspitze.
Positiv = Druckpunkt hinter dem Schwerpunkt = stabil.

Berechnet werden zwei Zeitpunkte: Start (volles Wasser) und leer.

Zwei Stufen (Entscheidung 6A, Chat 02.11.2026):
- stability_values: nur die Werte, ohne Urteil (für die API, Entscheidung 3B).
- check_stability: dieselben Werte plus Warnungen unter einer Schwelle.

Garantie von stability_values (Entscheidung 9x): entweder fünf endliche
Zahlen oder ein ValueError. Division durch null, Überlauf und NaN/unendlich
bei extremen Eingaben werden in ValueError umgewandelt. So kann die API
solche Eingaben mit 422 statt 500 beantworten.

Annahmen:
- Wasser bildet einen Zylinder mit Rumpfdurchmesser direkt am Heck
  (bei l_total). Die echte Flasche verjüngt sich zum Hals -> Näherung.
- x_cg_empty wird gemessen eingegeben (z. B. Rakete ausbalancieren).

Die Warnschwelle min_margin hat noch keine Quelle (Barrowman 1967 nennt
keine) und muss deshalb beim Aufruf übergeben werden [QUELLE PRÜFEN].
"""

from dataclasses import astuple, dataclass, field
from math import isfinite, pi

from app.physics.barrowman import center_of_pressure
from app.physics.waterphase import RHO_WATER


@dataclass
class StabilityValues:
    """Nur Werte, kein Urteil."""

    x_cp: float  # Druckpunkt in m ab Nasenspitze
    x_cg_start: float  # Schwerpunkt mit Startwasser in m
    x_cg_empty: float  # Schwerpunkt leer in m
    margin_start: float  # Stabilitätsmaß beim Start in Kalibern
    margin_empty: float  # Stabilitätsmaß leer in Kalibern


@dataclass
class StabilityResult:
    x_cp: float  # Druckpunkt in m ab Nasenspitze
    x_cg_start: float  # Schwerpunkt mit Startwasser
    x_cg_empty: float  # Schwerpunkt leer
    margin_start: float  # Stabilitätsmaß beim Start in Kalibern
    margin_empty: float  # Stabilitätsmaß leer in Kalibern
    min_margin: float  # verwendete Warnschwelle in Kalibern
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings


def check_mass_geometry(cfg) -> None:
    """ValueError mit Feldnamen, wenn Schwerpunktangaben fehlen oder unzulässig sind."""
    missing = [n for n in ("x_cg_empty", "l_total") if getattr(cfg, n) is None]
    if missing:
        raise ValueError(f"Geometrie fehlt: {', '.join(missing)}")
    if cfg.l_total <= 0:
        raise ValueError("l_total muss > 0 sein")
    if not 0 <= cfg.x_cg_empty <= cfg.l_total:
        raise ValueError("x_cg_empty muss zwischen 0 und l_total liegen")


def cg_with_water(cfg, v_water: float) -> float:
    """Schwerpunkt mit Wasser: gewichtetes Mittel aus Rakete und Wassersäule."""
    check_mass_geometry(cfg)
    if v_water < 0:
        raise ValueError("v_water darf nicht negativ sein")
    m_water = RHO_WATER * v_water
    if m_water == 0:
        return cfg.x_cg_empty
    height = v_water / (pi * cfg.d_body ** 2 / 4)  # Annahme: Zylinder
    if height > cfg.l_total:
        raise ValueError("Wassersäule ist länger als die Rakete")
    x_water = cfg.l_total - height / 2  # Mitte der Wassersäule am Heck
    return (cfg.m_empty * cfg.x_cg_empty + m_water * x_water) / (cfg.m_empty + m_water)


def stability_values(cfg) -> StabilityValues:
    """Druckpunkt, Schwerpunkte und Stabilitätsmaß beim Start und leer, ohne Urteil."""
    try:
        x_cp = center_of_pressure(cfg).x_cp
        x_start = cg_with_water(cfg, cfg.v_water0)
        x_empty = cg_with_water(cfg, 0.0)
        values = StabilityValues(
            x_cp=x_cp,
            x_cg_start=x_start,
            x_cg_empty=x_empty,
            margin_start=(x_cp - x_start) / cfg.d_body,
            margin_empty=(x_cp - x_empty) / cfg.d_body,
        )
    except ArithmeticError as err:  # ZeroDivisionError, OverflowError
        raise ValueError(
            f"Stabilität nicht berechenbar: Zahlenbereich überschritten ({type(err).__name__})"
        ) from err
    if not all(isfinite(v) for v in astuple(values)):
        raise ValueError("Stabilität nicht berechenbar: Ergebnis ist keine endliche Zahl")
    return values


def check_stability(cfg, min_margin: float) -> StabilityResult:
    """Stabilitätsmaß beim Start und leer; Warnung unter min_margin."""
    v = stability_values(cfg)
    warnings = []
    for label, margin in (("Start (mit Wasser)", v.margin_start), ("leer", v.margin_empty)):
        if margin < 0:
            warnings.append(
                f"{label}: instabil, Druckpunkt vor dem Schwerpunkt ({margin:.2f} Kaliber)"
            )
        elif margin < min_margin:
            warnings.append(
                f"{label}: Stabilitätsmaß {margin:.2f} Kaliber unter der Schwelle {min_margin:.2f}"
            )
    return StabilityResult(
        v.x_cp, v.x_cg_start, v.x_cg_empty, v.margin_start, v.margin_empty, min_margin, warnings
    )