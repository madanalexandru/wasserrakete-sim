"""Einstiegspunkt des FastAPI-Backends der Wasserraketen-Simulation."""

import os

from fastapi import FastAPI

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