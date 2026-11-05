"""Wächtertest: Ändert sich die Flugphysik, muss MODEL_VERSION steigen.

Jeder Flug speichert model_version (Kassenbon). Damit alte und neue
Ergebnisse sicher unterscheidbar bleiben, bildet dieser Test eine
Prüfsumme (SHA-256) über alle Dateien, die das Flugergebnis beeinflussen:
app/physics/*.py und app/search/*.py, OHNE barrowman.py und stability.py
(die Flugphysik nutzt die Geometrie nicht, siehe test_rocketconfig.py).
Neue Dateien in diesen Ordnern zählen automatisch mit.

Normalisiert werden nur Zeilenenden (CRLF -> LF), Leerzeichen am
Zeilenende und Leerzeilen am Dateiende, damit Windows und Linux dieselbe
Prüfsumme ergeben. Kommentare zählen mit (Preis: auch eine reine
Kommentaränderung verlangt eine neue Version).

Entscheidung 13γ, Chat 05.11.2026.

Wird test_physics_matches_model_version rot:
1. MODEL_VERSION in app/physics/simulation.py erhöhen (z. B. "1" -> "2"),
2. die neue Prüfsumme aus der Fehlermeldung als NEUEN Eintrag in
   KNOWN_MODEL_VERSIONS ergänzen (alte Einträge nie löschen),
3. Modelländerung mit Grund im projektlog festhalten.
"""

import hashlib
import shutil
from pathlib import Path

from app.physics.simulation import MODEL_VERSION

APP_DIR = Path(__file__).resolve().parent.parent / "app"
FLIGHT_DIRS = ("physics", "search")
NOT_FLIGHT = {"barrowman.py", "stability.py"}  # nur Stabilität, kein Flug

# Version -> Prüfsumme. Historie, wird nur ergänzt.
KNOWN_MODEL_VERSIONS = {
    "1": "45ae71963d2682470c2c49aa5e3a06ca1ac1d4db697a7a6d242564f5d89669eb",
}


def flight_files(app_dir: Path) -> list[Path]:
    """Alle Dateien, die das Flugergebnis beeinflussen, sortiert."""
    files = []
    for folder in FLIGHT_DIRS:
        files += [p for p in (app_dir / folder).glob("*.py") if p.name not in NOT_FLIGHT]
    return sorted(files, key=lambda p: p.relative_to(app_dir).as_posix())


def normalized(text: str) -> str:
    """Gleicher Text unabhängig von Zeilenenden und Editor-Gewohnheiten."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).rstrip("\n")


def physics_fingerprint(app_dir: Path = APP_DIR) -> str:
    """SHA-256 über Dateiname + normalisierten Inhalt aller Flugdateien."""
    digest = hashlib.sha256()
    for path in flight_files(app_dir):
        digest.update(path.relative_to(app_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized(path.read_text(encoding="utf-8")).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def test_physics_matches_model_version():
    current = physics_fingerprint()
    assert KNOWN_MODEL_VERSIONS.get(MODEL_VERSION) == current, (
        f"Flugphysik geändert, aber MODEL_VERSION = {MODEL_VERSION!r} passt nicht. "
        f"MODEL_VERSION erhöhen und Eintrag 'NEUE_VERSION': '{current}' in "
        f"KNOWN_MODEL_VERSIONS ergänzen (alte Einträge behalten)."
    )


def test_model_version_is_nonempty_string():
    assert isinstance(MODEL_VERSION, str) and MODEL_VERSION.strip()


def test_known_fingerprints_are_unique():
    # Verhindert, dass dieselbe Physik unter zwei Versionen läuft.
    values = list(KNOWN_MODEL_VERSIONS.values())
    assert len(values) == len(set(values))


def test_flight_files_cover_physics_and_search():
    names = {p.name for p in flight_files(APP_DIR)}
    assert {"simulation.py", "waterphase.py", "airphase.py", "freeflight.py",
            "integrator.py", "inverse.py", "binary_search.py"} <= names
    assert names.isdisjoint(NOT_FLIGHT)


# --- Gegenproben auf einer Kopie (tmp_path), das echte app/ bleibt unberührt ---

def copy_app(tmp_path: Path) -> Path:
    target = tmp_path / "app"
    for folder in FLIGHT_DIRS:
        shutil.copytree(APP_DIR / folder, target / folder,
                        ignore=shutil.ignore_patterns("__pycache__"))
    return target


def test_comment_change_in_waterphase_changes_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "physics" / "waterphase.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# Änderung\n", encoding="utf-8")
    assert physics_fingerprint(app_dir) != before


def test_change_in_search_changes_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "search" / "binary_search.py"
    path.write_text(path.read_text(encoding="utf-8") + "\nX = 1\n", encoding="utf-8")
    assert physics_fingerprint(app_dir) != before


def test_new_physics_file_changes_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    (app_dir / "physics" / "neu.py").write_text("Y = 2\n", encoding="utf-8")
    assert physics_fingerprint(app_dir) != before


def test_stability_change_keeps_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "physics" / "stability.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# egal\n", encoding="utf-8")
    assert physics_fingerprint(app_dir) == before


def test_line_endings_and_trailing_space_keep_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "physics" / "simulation.py"
    text = path.read_text(encoding="utf-8").replace("\n", "   \r\n") + "\r\n\r\n"
    path.write_bytes(text.encode("utf-8"))
    assert physics_fingerprint(app_dir) == before