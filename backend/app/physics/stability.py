"""Stabilitätsprüfung: Druckpunkt (Barrowman) gegen Schwerpunkt.

Nur eine Prüfung mit Warnung, nicht Teil der Flugphysik.
Stabilitätsmaß in Kalibern: (x_CP - x_CG) / d_body, Längen ab Nasenspitze.
Positiv = Druckpunkt hinter dem Schwerpunkt = stabil.

Geprüft werden zwei Zeitpunkte: Start (volles Wasser) und leer.

Annahmen:
- Wasser bildet einen Zylinder mit Rumpfdurchmesser direkt am Heck
  (bei l_total). Die echte Flasche verjüngt sich zum Hals -> Näherung.
- x_cg_empty wird gemessen eingegeben (z. B. Rakete ausbalancieren).

Die Warnschwelle min_margin hat noch keine Quelle (Barrowman 1967 nennt
keine) und muss deshalb beim Aufruf übergeben werden [QUELLE PRÜFEN].
"""

from dataclasses import dataclass, field
from math import pi

from app.physics.barrowman import center_of_pressure
from app.physics.waterphase import RHO_WATER


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


def check_stability(cfg, min_margin: float) -> StabilityResult:
    """Stabilitätsmaß beim Start und leer; Warnung unter min_margin."""
    x_cp = center_of_pressure(cfg).x_cp
    x_start = cg_with_water(cfg, cfg.v_water0)
    x_empty = cg_with_water(cfg, 0.0)
    m_start = (x_cp - x_start) / cfg.d_body
    m_empty = (x_cp - x_empty) / cfg.d_body

    warnings = []
    for label, margin in (("Start (mit Wasser)", m_start), ("leer", m_empty)):
        if margin < 0:
            warnings.append(
                f"{label}: instabil, Druckpunkt vor dem Schwerpunkt ({margin:.2f} Kaliber)"
            )
        elif margin < min_margin:
            warnings.append(
                f"{label}: Stabilitätsmaß {margin:.2f} Kaliber unter der Schwelle {min_margin:.2f}"
            )
    return StabilityResult(x_cp, x_start, x_empty, m_start, m_empty, min_margin, warnings)