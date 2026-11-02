"""Einstiegspunkt des FastAPI-Backends der Wasserraketen-Simulation.

Endpunkte nach „Full Stack Handwerk“: Pydantic-Modelle für Ein- und
Ausgabe (S. 80, 82), Statuscodes 201/404/422 (S. 78), eine
Datenbank-Session pro Request über Depends (S. 102).
"""

import os

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Rocket
from app.schemas import RocketCreate, RocketRead

# DEBUG kommt aus der .env (über docker-compose.yml).
# Nur bei DEBUG=true ist die API-Dokumentation unter /api/docs sichtbar.
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

app = FastAPI(
    title="Wasserraketen-Simulation",
    docs_url="/api/docs" if DEBUG else None,
    openapi_url="/api/openapi.json" if DEBUG else None,
    redoc_url=None,
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Lebenszeichen: Antwortet, wenn das Backend läuft."""
    return {"status": "ok"}


@app.post("/api/rockets", response_model=RocketRead, status_code=201)
def create_rocket(rocket_in: RocketCreate, session: Session = Depends(get_session)):
    """Legt eine Rakete an. Ungültige Eingaben lehnt RocketCreate mit 422 ab."""
    rocket = Rocket(**rocket_in.model_dump())
    session.add(rocket)
    session.commit()
    session.refresh(rocket)  # lädt id und created_at aus der Datenbank
    return rocket


@app.get("/api/rockets/{rocket_id}", response_model=RocketRead)
def read_rocket(rocket_id: int, session: Session = Depends(get_session)):
    """Gibt eine gespeicherte Rakete zurück, 404 bei unbekannter ID."""
    rocket = session.get(Rocket, rocket_id)
    if rocket is None:
        raise HTTPException(status_code=404, detail="Rakete nicht gefunden")
    return rocket