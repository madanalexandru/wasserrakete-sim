"""Einstiegspunkt des FastAPI-Backends der Wasserraketen-Simulation.

Endpunkte nach „Full Stack Handwerk“: Pydantic-Modelle für Ein- und
Ausgabe (S. 80, 82), Statuscodes 201/404/422 (S. 78), eine
Datenbank-Session pro Request über Depends (S. 102).

Stabilitätswerte (Chat Teil 4, 02.11.2026):
- Berechnet, nicht gespeichert, ohne Urteil (Entscheidungen 3B, 7a).
- Der Endpunkt rechnet selbst, beim POST VOR dem Speichern (Entscheidung
  8i). Scheitert die Rechnung, wird nichts gespeichert.
- Sicherheitsnetz nur im POST (Entscheidungen 9x, 10β): ValueError aus der
  Physik -> 422. Andere Fehler bleiben 500 (kein globaler Handler, damit
  Programmierfehler sichtbar bleiben). Im GET kein Netz: Ein Fehler dort
  liegt in gespeicherten Daten, nicht in der Anfrage -> 500.
"""

import os

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import GEOMETRY_FIELDS, Rocket
from app.physics.simulation import RocketConfig
from app.physics.stability import stability_values
from app.schemas import RocketCreate, RocketRead, StabilityRead

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
    return to_read(rocket, compute_stability(rocket.to_config()))  # kein Netz (10β)