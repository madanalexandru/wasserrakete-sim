"""Hilfen für Integrationstests gegen PostgreSQL (ohne Datenbankzugriff).

Liegen in einem eigenen Modul, damit der Schutz vor der falschen
Datenbank selbst ohne laufendes PostgreSQL getestet werden kann.
"""

from pathlib import Path

from alembic.config import Config
from sqlalchemy.engine import URL

# Nur wenn diese Variable "1" ist, laufen die Integrationstests.
ENABLE_VAR = "INTEGRATION_DB"

# Testdatenbanken müssen so enden; alles andere gilt als echte Daten.
TEST_DB_SUFFIX = "_test"

BACKEND_DIR = Path(__file__).resolve().parents[2]


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