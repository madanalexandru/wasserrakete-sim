"""Verbindung zur Datenbank (Engine und Session).

Nach „Full Stack Handwerk“, S. 99–101: Die Verbindungsadresse wird im
Code aus den Werten in .env gebaut; .env enthält keine fertige
DATABASE_URL. Abweichung vom Skript: URL.create statt f-String, damit
Sonderzeichen im Passwort (z. B. @ oder /) die Adresse nicht zerstören.

Die Engine wird erst beim ersten Aufruf von get_engine() erzeugt. So
lässt sich dieses Modul ohne Datenbank und ohne .env importieren
(wichtig für die Tests).
"""

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session

REQUIRED = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")


def database_url() -> URL:
    """Baut die Verbindungsadresse aus den Umgebungsvariablen."""
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Fehlende Umgebungsvariablen (siehe .env): {', '.join(missing)}")
    return URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "db"),  # Service-Name in docker-compose.yml
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )


@lru_cache
def get_engine() -> Engine:
    """Eine Engine (Verbindungspool) für die ganze Anwendung."""
    return create_engine(database_url(), pool_pre_ping=True)


def get_session():
    """Eine Session pro Request, für FastAPI über Depends (Skript S. 102)."""
    with Session(get_engine()) as session:
        yield session