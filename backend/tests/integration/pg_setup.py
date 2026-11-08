"""Hilfen für Integrationstests gegen PostgreSQL.

Liegen in einem eigenen Modul, damit der Schutz vor der falschen
Datenbank selbst ohne laufendes PostgreSQL getestet werden kann. Keine
Funktion hier baut selbst eine Verbindung auf.
"""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import URL

# Nur wenn diese Variable "1" ist, laufen die Integrationstests.
ENABLE_VAR = "INTEGRATION_DB"

# Testdatenbanken müssen so enden; alles andere gilt als echte Daten.
TEST_DB_SUFFIX = "_test"

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Reihenfolge egal, CASCADE folgt den Fremdschlüsseln.
TABLES = ("flights", "series", "rockets")


def require_test_database(url: URL) -> None:
    """Bricht ab, wenn die Adresse nicht auf eine Testdatenbank zeigt.

    Die Tests leeren alle Tabellen. Ein Konfigurationsfehler darf deshalb
    nie die Datenbank mit echten Experimentdaten treffen.
    """
    name = url.database or ""
    if not name.endswith(TEST_DB_SUFFIX):
        raise RuntimeError(
            f"Integrationstests abgebrochen: Datenbank '{name}' endet nicht auf "
            f"'{TEST_DB_SUFFIX}'. Tests laufen nur gegen eine Testdatenbank."
        )


def alembic_config() -> Config:
    """Alembic-Einstellungen wie in alembic.ini, aber ohne Logging-Teil.

    alembic.ini würde über fileConfig die Logging-Einstellungen des ganzen
    Testprozesses ersetzen. Die Verbindungsadresse kommt wie im Betrieb aus
    app/db.py (über alembic/env.py).
    """
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("path_separator", "os")
    return config


def truncate_all(engine) -> None:
    """Leert alle Tabellen und setzt die IDs auf 1 zurück."""
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


def count_rows(engine, *tables: str) -> tuple[int, ...]:
    """Anzahl der Zeilen je Tabelle, in der angegebenen Reihenfolge."""
    with engine.connect() as connection:
        return tuple(
            connection.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            for table in tables
        )


class Hidden(dict):
    """dict, dessen Anzeige keine Inhalte zeigt.

    pytest gibt bei einem Fehlschlag die Argumente der Testfunktion aus.
    Prüfabläufe legen ihre Daten (auch Ergebniswerte) deshalb hier ab;
    angezeigt wird nur die Anzahl der Einträge.
    """

    def __repr__(self) -> str:
        return f"<Hidden: {len(self)} Eintraege>"