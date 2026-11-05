"""API-Schemas (Pydantic): was der Client schicken darf und was zurückkommt.

Nach „Full Stack Handwerk“, S. 80: Pydantic prüft Eingaben an der Grenze;
ungültige Anfragen beantwortet FastAPI mit 422, bevor der Endpunkt läuft.
Alle Werte in SI-Einheiten, Feldnamen wie RocketConfig und die Spalten in
app/models.py (prüft tests/test_schemas.py).

Regeln:
- Einfache Regeln (> 0, 3 oder 4 Finnen, ...) stehen als Feld-Grenzen hier,
  damit sie in /api/docs sichtbar sind.
- Die Geometrie-Regeln über mehrere Felder (Schwerpunkt innerhalb der
  Rakete, Wassersäule nicht länger als die Rakete, Barrowman-Grenzen) prüft
  die Physik selbst: Das Schema ruft stability_values auf, statt die Regeln
  nachzubauen. So steht jede dieser Regeln nur einmal im Code.
  stability_values liefert nur endliche Werte oder einen ValueError;
  extreme Eingaben (z. B. d_body = 1e-200) ergeben so 422 statt 500.
- Keine Obergrenzen: Für Grenzwerte gibt es (noch) keine Quelle.
- d_nozzle < d_body ist eine reine Geometrie-Regel; die Physik prüft sie nicht.

Antworten:
- RocketRead enthält das Feld stability (berechnet, nicht gespeichert, ohne
  Urteil). Ohne Geometrie ist es null. Gefüllt wird es im Endpunkt
  (app/main.py).
- FlightRead ist der vollständige Kassenbon eines Flugs: Kopf (id, Zeit,
  Rakete, Serie, model_version), Kopie der Konfiguration, Felder des
  inversen Modus (null im Vorwärtsmodus) und Ergebnis. Die Flugkurve gehört
  nicht dazu, sie wird nicht gespeichert. Die Feldreihenfolge ist zugleich
  die Spaltenreihenfolge für den späteren CSV-Export (prüft
  tests/test_flight_read.py).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import GEOMETRY_FIELDS
from app.physics.airphase import T_START
from app.physics.simulation import RocketConfig
from app.physics.stability import stability_values


class RocketCreate(BaseModel):
    """Eingabe für POST /api/rockets: Name + Konfiguration wie RocketConfig."""

    # extra="forbid": Tippfehler wie "fin_sweeep" ergeben 422 statt stiller Ignoranz.
    # allow_inf_nan=False: NaN und unendlich sind keine gültigen Messwerte.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: str = Field(min_length=1, description="Frei wählbarer Name")

    # Pflichtfelder für die Flugsimulation
    v_bottle: float = Field(gt=0, description="Flaschenvolumen in m³")
    v_water0: float = Field(gt=0, description="Wasservolumen beim Start in m³")
    p0_gauge: float = Field(gt=0, description="Startdruck als Überdruck in Pa")
    d_nozzle: float = Field(gt=0, description="Düsendurchmesser in m")
    m_empty: float = Field(gt=0, description="Leermasse in kg")
    c_w: float = Field(ge=0, description="Luftwiderstandsbeiwert (0 = ohne Luftwiderstand)")
    d_body: float = Field(gt=0, description="Rumpfdurchmesser in m")
    temp0: float = Field(default=T_START, gt=0, description="Lufttemperatur beim Start in K")

    # Geometrie (Barrowman): alle zehn Felder oder keines.
    # Grenzen wie in app/physics/barrowman.py und stability.py.
    nose_shape: Literal["cone", "ogive"] | None = None
    l_nose: float | None = Field(default=None, gt=0, description="Länge Nasenkegel in m")
    n_fins: Literal[3, 4] | None = None
    fin_root_chord: float | None = Field(default=None, gt=0, description="c_r in m")
    fin_tip_chord: float | None = Field(default=None, ge=0, description="c_t in m")
    fin_span: float | None = Field(default=None, gt=0, description="s in m")
    fin_sweep: float | None = Field(default=None, description="x_t in m")
    x_fin: float | None = Field(default=None, ge=0, description="Nasenspitze bis Finne in m")
    x_cg_empty: float | None = Field(default=None, ge=0, description="Schwerpunkt leer in m")
    l_total: float | None = Field(default=None, gt=0, description="Gesamtlänge in m")

    def to_config(self) -> RocketConfig:
        """Schema -> RocketConfig, damit die Physik damit rechnen kann."""
        return RocketConfig(**self.model_dump(exclude={"name"}))

    @model_validator(mode="after")
    def check_combinations(self):
        # Gleiche Regel wie in simulate_waterphase (dort erst beim Simulieren geprüft).
        if self.v_water0 >= self.v_bottle:
            raise ValueError("v_water0 muss kleiner als v_bottle sein")
        if self.d_nozzle >= self.d_body:
            raise ValueError("d_nozzle muss kleiner als d_body sein")

        missing = [name for name in GEOMETRY_FIELDS if getattr(self, name) is None]
        if len(missing) == len(GEOMETRY_FIELDS):
            return self  # keine Geometrie angegeben: erlaubt
        if missing:
            raise ValueError(f"Geometrie unvollständig, es fehlen: {', '.join(missing)}")

        # Geometrie vollständig: Regeln der Physik direkt anwenden.
        # stability_values prüft Geometrie, Schwerpunkt und Wassersäule und
        # wirft ValueError, wenn die Werte nicht endlich berechenbar sind.
        stability_values(self.to_config())
        return self


class StabilityRead(BaseModel):
    """Stabilitätswerte nach Barrowman, berechnet, ohne Urteil."""

    # from_attributes=True: liest die Werte direkt aus StabilityValues.
    model_config = ConfigDict(from_attributes=True)

    x_cp: float = Field(description="Druckpunkt in m ab Nasenspitze")
    x_cg_start: float = Field(description="Schwerpunkt mit Startwasser in m ab Nasenspitze")
    x_cg_empty: float = Field(description="Schwerpunkt leer in m ab Nasenspitze")
    margin_start: float = Field(description="Stabilitätsmaß beim Start in Kalibern")
    margin_empty: float = Field(description="Stabilitätsmaß leer in Kalibern")


class RocketRead(BaseModel):
    """Antwort: gespeicherte Rakete mit ID, Zeitstempel und Stabilitätswerten."""

    # from_attributes=True: liest die Werte direkt aus der SQLAlchemy-Zeile.
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    v_bottle: float
    v_water0: float
    p0_gauge: float
    d_nozzle: float
    m_empty: float
    c_w: float
    d_body: float
    temp0: float
    nose_shape: str | None
    l_nose: float | None
    n_fins: int | None
    fin_root_chord: float | None
    fin_tip_chord: float | None
    fin_span: float | None
    fin_sweep: float | None
    x_fin: float | None
    x_cg_empty: float | None
    l_total: float | None
    # Berechnet, nicht gespeichert; null ohne Geometrie
    stability: StabilityRead | None = None


class FlightRead(BaseModel):
    """Antwort: ein gespeicherter Flug als vollständiger Kassenbon."""

    # from_attributes=True: liest die Werte direkt aus der SQLAlchemy-Zeile.
    model_config = ConfigDict(from_attributes=True)

    # Kopf
    id: int
    created_at: datetime
    rocket_id: int
    series_id: int | None  # null = Einzelflug
    model_version: str
    # Kopie der Konfiguration, mit der gerechnet wurde (SI, wie RocketConfig)
    v_bottle: float
    v_water0: float
    p0_gauge: float
    d_nozzle: float
    m_empty: float
    c_w: float
    d_body: float
    temp0: float
    nose_shape: str | None
    l_nose: float | None
    n_fins: int | None
    fin_root_chord: float | None
    fin_tip_chord: float | None
    fin_span: float | None
    fin_sweep: float | None
    x_fin: float | None
    x_cg_empty: float | None
    l_total: float | None
    # Nur im inversen Modus gefüllt, sonst null
    target_apogee: float | None
    searcher: str | None
    search_evaluations: int | None
    # Ergebnis wie FlightResult, ohne Flugkurve
    apogee: float = Field(description="Apogäum in m")
    t_apogee: float = Field(description="Zeitpunkt des Apogäums in s")
    t_water_end: float = Field(description="Ende Wasserschub in s")
    t_air_end: float = Field(description="Ende Luftstoß in s")
    v_burnout: float = Field(description="Geschwindigkeit am Ende des Schubs in m/s")
    h_burnout: float = Field(description="Höhe am Ende des Schubs in m")
    water_rest: float = Field(description="Nicht ausgestoßenes Wasser in m³")