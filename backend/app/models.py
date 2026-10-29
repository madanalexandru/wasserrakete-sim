"""Datenmodell: Raketen, Experimentserien und Flüge (SQLAlchemy).

Tabellen als Python-Klassen nach „Full Stack Handwerk“, S. 99–100.
Jeder Flug speichert eine Kopie der Konfiguration, mit der er gerechnet
wurde. So bleibt er reproduzierbar, und der CSV-Export
braucht keinen Join. Die Konfig-Spalten heißen wie die Felder von
RocketConfig; alle Werte in SI-Einheiten.

Die Verbindung zur Datenbank (Engine, Session) folgt in einem eigenen
Schritt. Diese Datei beschreibt nur die Tabellen.
"""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base

from app.physics.simulation import RocketConfig

Base = declarative_base()

# Pflichtfelder: nötig für die Flugsimulation (NOT NULL).
REQUIRED_CONFIG_FIELDS = (
    "v_bottle", "v_water0", "p0_gauge", "d_nozzle",
    "m_empty", "c_w", "d_body", "temp0",
)

# Geometrie für die Barrowman-Prüfung: optional (NULL erlaubt).
# Alte Zeilen aus der Zeit vor der 2. Migration haben hier NULL.
GEOMETRY_FIELDS = (
    "nose_shape", "l_nose", "n_fins", "fin_root_chord", "fin_tip_chord",
    "fin_span", "fin_sweep", "x_fin", "x_cg_empty", "l_total",
)

# Muss genau den Feldern von RocketConfig entsprechen (prüft test_models.py).
CONFIG_FIELDS = REQUIRED_CONFIG_FIELDS + GEOMETRY_FIELDS


def config_values(cfg: RocketConfig) -> dict:
    """RocketConfig -> Spaltenwerte, z. B. Rocket(name="A", **config_values(cfg))."""
    return {name: getattr(cfg, name) for name in CONFIG_FIELDS}


class ConfigColumns:
    """Spaltenblock der Konfiguration, gemeinsam für Rakete und Flug."""

    v_bottle = Column(Float, nullable=False)  # Flaschenvolumen in m³
    v_water0 = Column(Float, nullable=False)  # Wasservolumen beim Start in m³
    p0_gauge = Column(Float, nullable=False)  # Startdruck als Überdruck in Pa
    d_nozzle = Column(Float, nullable=False)  # Düsendurchmesser in m
    m_empty = Column(Float, nullable=False)  # Leermasse in kg
    c_w = Column(Float, nullable=False)  # Luftwiderstandsbeiwert
    d_body = Column(Float, nullable=False)  # Rumpfdurchmesser in m
    temp0 = Column(Float, nullable=False)  # Lufttemperatur beim Start in K

    # Geometrie (Barrowman-Prüfung), Längen in m ab Nasenspitze
    nose_shape = Column(String)  # "cone" oder "ogive"
    l_nose = Column(Float)  # Länge des Nasenkegels
    n_fins = Column(Integer)  # 3 oder 4
    fin_root_chord = Column(Float)  # c_r
    fin_tip_chord = Column(Float)  # c_t
    fin_span = Column(Float)  # s
    fin_sweep = Column(Float)  # x_t
    x_fin = Column(Float)  # l_T
    x_cg_empty = Column(Float)  # Schwerpunkt leer
    l_total = Column(Float)  # Gesamtlänge

    def to_config(self) -> RocketConfig:
        """Zeile -> RocketConfig, damit der Flug neu gerechnet werden kann."""
        return RocketConfig(**{name: getattr(self, name) for name in CONFIG_FIELDS})


class Rocket(ConfigColumns, Base):
    """Raketen-Vorlage. Wird nach dem Anlegen nicht mehr verändert."""

    __tablename__ = "rockets"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Series(Base):
    """Experimentserie: ein Parameter wird in n_steps Schritten variiert."""

    __tablename__ = "series"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    rocket_id = Column(Integer, ForeignKey("rockets.id"), nullable=False)
    mode = Column(String, nullable=False)  # "forward" oder "inverse"
    param_name = Column(String, nullable=False)  # z. B. "p0_gauge" oder "target_apogee"
    param_start = Column(Float, nullable=False)
    param_stop = Column(Float, nullable=False)
    n_steps = Column(Integer, nullable=False)
    searcher = Column(String)  # Suchverfahren, nur im inversen Modus
    duration_s = Column(Float)  # Laufzeit der ganzen Serie, für den Durchsatz


class Flight(ConfigColumns, Base):
    """Ein simulierter Flug = eine Zeile im CSV-Export."""

    __tablename__ = "flights"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    rocket_id = Column(Integer, ForeignKey("rockets.id"), nullable=False)
    series_id = Column(Integer, ForeignKey("series.id"), index=True)  # leer = Einzelflug
    model_version = Column(String, nullable=False)  # macht Modelländerungen nachvollziehbar

    # Nur im inversen Modus gefüllt
    target_apogee = Column(Float)  # Zielhöhe in m
    searcher = Column(String)
    search_evaluations = Column(Integer)  # Anzahl Flüge der Suche

    # Ergebnis, Felder wie FlightResult (ohne trajectory)
    apogee = Column(Float, nullable=False)  # m
    t_apogee = Column(Float, nullable=False)  # s
    t_water_end = Column(Float, nullable=False)  # s
    t_air_end = Column(Float, nullable=False)  # s
    v_burnout = Column(Float, nullable=False)  # m/s
    h_burnout = Column(Float, nullable=False)  # m
    water_rest = Column(Float, nullable=False)  # m³