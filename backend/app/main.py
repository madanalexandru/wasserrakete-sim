"""Einstiegspunkt des FastAPI-Backends der Wasserraketen-Simulation.

Endpunkte nach „Full Stack Handwerk“: Pydantic-Modelle für Ein- und
Ausgabe (S. 80, 82), Statuscodes 201/404/422 (S. 78), eine
Datenbank-Session pro Request über Depends (S. 102).

Raketen (POST/GET /api/rockets):
- Stabilitätswerte werden berechnet, nicht gespeichert, ohne Urteil.
- Der Endpunkt rechnet sie selbst, beim POST VOR dem Speichern. Scheitert
  die Rechnung, wird nichts gespeichert.
- Sicherheitsnetz nur im POST: ValueError aus der Physik -> 422. Andere
  Fehler bleiben 500 (kein globaler Handler, damit Programmierfehler
  sichtbar bleiben). Im GET kein Netz: Ein Fehler dort liegt in
  gespeicherten Daten, nicht in der Anfrage -> 500.

Flüge (POST /api/rockets/{id}/flights):
- Rechnet einen Flug mit der gespeicherten Konfiguration und speichert ihn
  als Kassenbon: Kopie der Konfiguration, Ergebnis ohne Flugkurve,
  model_version.
- Kein Body: Der Flug nutzt genau die Werte der Rakete. Andere Werte
  -> neue Rakete oder Serie.
- Sicherheitsnetz: ValueError und RuntimeError aus simulate_flight -> 422,
  nichts gespeichert. Die Rakete ist gültig, liegt aber außerhalb dessen,
  was das Modell rechnen kann (z. B. „max_steps zu klein“). Andere Fehler
  bleiben 500.

Flug abrufen (GET /api/flights/{id}):
- Liefert die gespeicherten Werte unverändert, auch bei einer älteren
  model_version. Nichts wird neu gerechnet, daher kein Sicherheitsnetz:
  Ein Fehler beim Lesen bleibt 500.
- Unbekannte ID -> 404, wie beim Abruf einer Rakete. Eine Liste der Flüge
  gibt es nicht; große Mengen laufen über Serien und den CSV-Export.

Serie starten (POST /api/rockets/{id}/series):
- Variiert einen Parameter der gespeicherten Rakete (SeriesCreate) und
  speichert jeden Flug als Kassenbon mit series_id. Vorerst nur der
  Vorwärtsmodus.
- Reihenfolge: erst alle Schritte vorab prüfen (wie beim Anlegen einer
  Rakete), dann alle Flüge rechnen, dann alles in einer Transaktion
  speichern. Scheitert ein Schritt, antwortet die API mit 422 und der
  Schrittnummer, und es wird nichts gespeichert, auch nicht die Serie.
- Ungültiger Schritt -> 422 mit type "value_error"; ValueError oder
  RuntimeError der Simulation -> 422 mit type "simulation_error". Andere
  Fehler bleiben 500.
- duration_s = Rechnen aller Flüge + Schreiben in die Datenbank (bis nach
  flush), gemessen mit perf_counter. Nicht enthalten: Vorabprüfung und
  Commit.
- Synchron: Die Antwort kommt erst, wenn alle Flüge gespeichert sind.
  Die Höchstzahl der Schritte steht in SeriesCreate.

Serie abrufen (GET /api/series/{id}):
- Liefert die gespeicherte Serie ohne Flugliste; die Flüge kommen über den
  CSV-Export. Unbekannte ID -> 404, kein Sicherheitsnetz.

CSV-Export (GET /api/series/{id}/flights.csv):
- Alle Flüge der Serie als CSV, eine Zeile pro Flug, Spalten wie FlightRead
  (Format siehe app/export.py). Sortiert nach dem variierten Parameter,
  bei Gleichstand nach id; die Zeilen stehen damit in der Schrittfolge,
  unabhängig davon, in welcher Reihenfolge die Datenbank die IDs vergibt.
- Ganze Antwort statt Streaming: Die CSV wird vollständig erzeugt, bevor
  etwas gesendet wird. Ein Fehler beim Lesen ergibt 500 statt einer
  abgeschnittenen Datei mit Status 200.
- Download als serie_<id>.csv. Unbekannte ID -> 404 wie beim Abruf der
  Serie; kein Sicherheitsnetz, weil nichts gerechnet wird.
"""

import os
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.export import flights_to_csv
from app.models import GEOMETRY_FIELDS, Flight, Rocket, Series, config_values, result_values
from app.physics.simulation import MODEL_VERSION, RocketConfig, simulate_flight
from app.physics.stability import stability_values
from app.schemas import (
    FlightRead, RocketCreate, RocketRead, SeriesCreate, SeriesRead, SeriesStepError,
    StabilityRead,
)

# DEBUG kommt aus der .env (über docker-compose.yml).
# Nur bei DEBUG=true ist die API-Dokumentation unter /api/docs sichtbar.
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

app = FastAPI(
    title="Wasserraketen-Simulation",
    docs_url="/api/docs" if DEBUG else None,
    openapi_url="/api/openapi.json" if DEBUG else None,
    redoc_url=None,
)


def compute_stability(cfg: RocketConfig) -> StabilityRead | None:
    """Stabilitätswerte oder None, wenn die Rakete keine Geometrie hat.

    Ist nur ein Teil der Geometrie da, wirft stability_values einen
    ValueError (über die API nicht möglich, das Schema verlangt alles
    oder nichts).
    """
    if all(getattr(cfg, name) is None for name in GEOMETRY_FIELDS):
        return None
    return StabilityRead.model_validate(stability_values(cfg))


def to_read(rocket: Rocket, stability: StabilityRead | None) -> RocketRead:
    """Gespeicherte Zeile + berechnete Stabilitätswerte -> Antwort."""
    return RocketRead.model_validate(rocket).model_copy(update={"stability": stability})


@app.get("/api/health")
def health() -> dict[str, str]:
    """Lebenszeichen: Antwortet, wenn das Backend läuft."""
    return {"status": "ok"}


@app.post("/api/rockets", response_model=RocketRead, status_code=201)
def create_rocket(rocket_in: RocketCreate, session: Session = Depends(get_session)):
    """Legt eine Rakete an. Ungültige Eingaben lehnt RocketCreate mit 422 ab."""
    try:
        stability = compute_stability(rocket_in.to_config())  # vor dem Speichern
    except ValueError as err:
        # Sicherheitsnetz: gleiche Form wie die 422-Antworten von FastAPI
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(err), "type": "value_error"}],
        ) from err
    rocket = Rocket(**rocket_in.model_dump())
    session.add(rocket)
    session.commit()
    session.refresh(rocket)  # lädt id und created_at aus der Datenbank
    return to_read(rocket, stability)


@app.get("/api/rockets/{rocket_id}", response_model=RocketRead)
def read_rocket(rocket_id: int, session: Session = Depends(get_session)):
    """Gibt eine gespeicherte Rakete zurück, 404 bei unbekannter ID."""
    rocket = session.get(Rocket, rocket_id)
    if rocket is None:
        raise HTTPException(status_code=404, detail="Rakete nicht gefunden")
    return to_read(rocket, compute_stability(rocket.to_config()))  # kein Netz, siehe oben


@app.post("/api/rockets/{rocket_id}/flights", response_model=FlightRead, status_code=201)
def create_flight(rocket_id: int, session: Session = Depends(get_session)):
    """Simuliert einen Flug der Rakete und speichert ihn, 404 bei unbekannter ID."""
    rocket = session.get(Rocket, rocket_id)
    if rocket is None:
        raise HTTPException(status_code=404, detail="Rakete nicht gefunden")
    cfg = rocket.to_config()
    try:
        result = simulate_flight(cfg)  # vor dem Speichern
    except (ValueError, RuntimeError) as err:
        # Sicherheitsnetz: gleiche Form wie die 422-Antworten von FastAPI
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["path", "rocket_id"], "msg": str(err), "type": "simulation_error"}],
        ) from err
    flight = Flight(
        rocket_id=rocket.id,
        model_version=MODEL_VERSION,
        **config_values(cfg),
        **result_values(result),
    )
    session.add(flight)
    session.commit()
    session.refresh(flight)  # lädt id und created_at aus der Datenbank
    return flight


@app.get("/api/flights/{flight_id}", response_model=FlightRead)
def read_flight(flight_id: int, session: Session = Depends(get_session)):
    """Gibt einen gespeicherten Flug zurück, 404 bei unbekannter ID."""
    flight = session.get(Flight, flight_id)
    if flight is None:
        raise HTTPException(status_code=404, detail="Flug nicht gefunden")
    return flight  # gespeicherter Kassenbon, nichts neu gerechnet


def step_error(step: int, msg: str, error_type: str) -> HTTPException:
    """422 im Format von FastAPI, mit der Nummer des gescheiterten Schritts."""
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["body", "steps", step], "msg": msg, "type": error_type}],
    )


@app.post("/api/rockets/{rocket_id}/series", response_model=SeriesRead, status_code=201)
def create_series(
    rocket_id: int, series_in: SeriesCreate, session: Session = Depends(get_session)
):
    """Rechnet alle Flüge einer Serie und speichert sie, 404 bei unbekannter Rakete."""
    rocket = session.get(Rocket, rocket_id)
    if rocket is None:
        raise HTTPException(status_code=404, detail="Rakete nicht gefunden")

    # 1. Alle Schritte vorab prüfen, bevor irgendetwas gerechnet wird
    try:
        configs = series_in.step_configs(rocket.to_config())
    except SeriesStepError as err:
        raise step_error(err.step, str(err), "value_error") from err

    # 2. Alle Flüge rechnen; noch nichts in der Session
    start = perf_counter()
    results = []
    for step, cfg in enumerate(configs):
        try:
            results.append(simulate_flight(cfg))
        except (ValueError, RuntimeError) as err:
            value = getattr(cfg, series_in.param_name)
            msg = f"Schritt {step} ({series_in.param_name} = {value!r}): {err}"
            raise step_error(step, msg, "simulation_error") from err

    # 3. Serie und Flüge schreiben; erst der Commit macht alles sichtbar
    series = Series(rocket_id=rocket.id, **series_in.model_dump())
    session.add(series)
    session.flush()  # vergibt series.id für die Flüge
    session.add_all(
        Flight(
            rocket_id=rocket.id,
            series_id=series.id,
            model_version=MODEL_VERSION,
            **config_values(cfg),
            **result_values(result),
        )
        for cfg, result in zip(configs, results)
    )
    session.flush()  # alle Flüge an die Datenbank gesendet
    series.duration_s = perf_counter() - start
    session.commit()
    session.refresh(series)  # lädt created_at aus der Datenbank
    return series


@app.get("/api/series/{series_id}", response_model=SeriesRead)
def read_series(series_id: int, session: Session = Depends(get_session)):
    """Gibt eine gespeicherte Serie zurück (ohne Flüge), 404 bei unbekannter ID."""
    series = session.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Serie nicht gefunden")
    return series


@app.get(
    "/api/series/{series_id}/flights.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Flüge der Serie als CSV"}},
)
def export_series_csv(series_id: int, session: Session = Depends(get_session)):
    """Alle Flüge einer Serie als CSV-Datei, 404 bei unbekannter ID."""
    series = session.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Serie nicht gefunden")
    varied = getattr(Flight, series.param_name)  # Spalte des variierten Parameters
    query = (
        select(Flight)
        .where(Flight.series_id == series.id)
        .order_by(varied, Flight.id)
    )
    text = flights_to_csv(session.scalars(query))  # vollständig, vor dem Senden
    return Response(
        content=text,
        media_type="text/csv",  # Starlette ergänzt "; charset=utf-8"
        headers={"Content-Disposition": f'attachment; filename="serie_{series.id}.csv"'},
    )