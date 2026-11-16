"""Wächtertest: Ändert sich die Flugphysik, muss MODEL_VERSION steigen.

Jeder Flug speichert model_version. Damit alte und neue Ergebnisse
sicher unterscheidbar bleiben, bildet dieser Test eine Prüfsumme
(SHA-256) über alle Dateien, die das Flugergebnis beeinflussen:
app/physics/*.py und app/search/*.py, ohne barrowman.py und stability.py
(die Flugphysik nutzt die Geometrie nicht, siehe test_rocketconfig.py).
Neue Dateien in diesen Ordnern zählen automatisch mit.

Gehasht wird der Syntaxbaum (ast), nicht der Quelltext. Kommentare,
Docstrings, Leerzeilen, Einrückungsstil und Zeilenenden ändern die
Prüfsumme daher nicht; jede Änderung an Code, Konstanten oder Dateinamen
schon. Die eigene Ausgabe des Baums (tree_text) lässt leere Felder weg,
damit Python 3.11 bis 3.13 dieselbe Prüfsumme ergeben.

Wird test_physics_matches_model_version rot:
1. MODEL_VERSION in app/physics/simulation.py erhöhen (z. B. "1" -> "2"),
2. die neue Prüfsumme aus der Fehlermeldung als neuen Eintrag in
   KNOWN_MODEL_VERSIONS ergänzen (alte Einträge nie löschen),
3. Modelländerung mit Grund dokumentieren.
"""

import ast
import hashlib
import shutil
from pathlib import Path

from app.physics.simulation import MODEL_VERSION

APP_DIR = Path(__file__).resolve().parent.parent / "app"
FLIGHT_DIRS = ("physics", "search")
NOT_FLIGHT = {"barrowman.py", "stability.py"}  # nur Stabilität, kein Flug

# Version -> Prüfsumme des Syntaxbaums. Wird nur ergänzt.
# Bis Commit 73e639e wurde der Quelltext samt Kommentaren gehasht;
# Version "1" hatte damals die Prüfsumme
# e724ffc424e1878e27e46545b04880d5f0875b4a73aad1d024bcefa381e99180.
# Der Syntaxbaum ist seit Commit 475307d (Eintrag von "1") unverändert.
KNOWN_MODEL_VERSIONS = {
    "1": "34e4c1d3590b1ee25d813b7ea0f0e102a65524274fd36bd187a2603e99220c3b",
}

DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def flight_files(app_dir: Path) -> list[Path]:
    """Alle Dateien, die das Flugergebnis beeinflussen, sortiert."""
    files = []
    for folder in FLIGHT_DIRS:
        files += [p for p in (app_dir / folder).glob("*.py") if p.name not in NOT_FLIGHT]
    return sorted(files, key=lambda p: p.relative_to(app_dir).as_posix())


def without_docstrings(tree: ast.AST) -> ast.AST:
    """Entfernt Docstrings aus Modul, Klassen und Funktionen."""
    for node in ast.walk(tree):
        if isinstance(node, DOCSTRING_OWNERS):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return tree


def tree_text(node) -> str:
    """Textform des Baums ohne Positionen und ohne leere Felder."""
    if isinstance(node, ast.AST):
        parts = []
        for field in node._fields:
            value = getattr(node, field, None)
            if value is None or value == []:
                continue
            parts.append(f"{field}={tree_text(value)}")
        return f"{type(node).__name__}({','.join(parts)})"
    if isinstance(node, list):
        return "[" + ",".join(tree_text(item) for item in node) + "]"
    return repr(node)


def code_text(source: str) -> str:
    """Code einer Datei ohne Kommentare und Docstrings."""
    return tree_text(without_docstrings(ast.parse(source)))


def physics_fingerprint(app_dir: Path = APP_DIR) -> str:
    """SHA-256 über Dateiname + Syntaxbaum aller Flugdateien."""
    digest = hashlib.sha256()
    for path in flight_files(app_dir):
        digest.update(path.relative_to(app_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(code_text(path.read_text(encoding="utf-8")).encode("utf-8"))
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


def test_tree_text_is_fixed():
    # Feste Erwartung: Ändert eine Python-Version die Baumform, fällt das
    # hier auf und nicht erst als scheinbare Physikänderung.
    source = '"""Doc."""\nX = 1  # Kommentar\n\ndef f(a):\n    """Doc."""\n    return a * X\n'
    assert code_text(source) == (
        "Module(body=[Assign(targets=[Name(id='X',ctx=Store())],value=Constant(value=1)),"
        "FunctionDef(name='f',args=arguments(args=[arg(arg='a')]),"
        "body=[Return(value=BinOp(left=Name(id='a',ctx=Load()),op=Mult(),"
        "right=Name(id='X',ctx=Load())))])])"
    )


# --- Gegenproben auf einer Kopie (tmp_path), das echte app/ bleibt unberührt ---

def copy_app(tmp_path: Path) -> Path:
    target = tmp_path / "app"
    for folder in FLIGHT_DIRS:
        shutil.copytree(APP_DIR / folder, target / folder,
                        ignore=shutil.ignore_patterns("__pycache__"))
    return target


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_comment_change_keeps_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "physics" / "waterphase.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# Änderung\n", encoding="utf-8")
    assert physics_fingerprint(app_dir) == before


def test_docstring_change_keeps_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    edit(app_dir / "physics" / "simulation.py",
         '"""Gesamtflug:', '"""Geänderter Docstring. Gesamtflug:')
    assert physics_fingerprint(app_dir) == before


def test_crlf_and_trailing_spaces_keep_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "physics" / "freeflight.py"
    text = path.read_text(encoding="utf-8")
    path.write_bytes(text.replace("\n", "   \r\n").encode("utf-8"))
    assert physics_fingerprint(app_dir) == before


def test_constant_change_changes_fingerprint(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    edit(app_dir / "physics" / "simulation.py", "c_w=0.5,", "c_w=0.51,")
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


def test_stability_files_do_not_count(tmp_path):
    app_dir = copy_app(tmp_path)
    before = physics_fingerprint(app_dir)
    path = app_dir / "physics" / "stability.py"
    path.write_text(path.read_text(encoding="utf-8") + "\nZ = 3\n", encoding="utf-8")
    assert physics_fingerprint(app_dir) == before