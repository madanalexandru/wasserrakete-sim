"""Analytische Lösung F1/F2: Einzelflüge R0 bis R9 über die API rechnen und speichern.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitt 1, Nachtrag 5)

Je Rakete werden zwei neue Raketen angelegt und je ein Einzelflug gerechnet:
F1 mit c_w = 0 (Freiflug ohne Widerstand), F2 mit c_w = 0,345 (c_ref).
Sonst gilt die Nennkonfiguration wie in durchsatz/run.py; temp0 wird nicht
gesendet (Standard der API). Die JSON-Antworten (FlightRead) werden byteweise
unverändert in data/ gespeichert, dazu manifest.csv.

Antwortet die API auf einen Flug mit 422, ist das ein Messergebnis: Die Zeile
wird mit Status und Fehlertext gespeichert (Rakete "nicht auswertbar") und
die Messung geht weiter. Andere Fehler brechen ohne Schreiben ab.

Das Skript gibt bewusst keine Ergebnisse aus (keine Apogäen, keine
Brennschluss-Werte).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python analytisch/run.py
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("API_BASE", "http://frontend/api")
DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST_NAME = "manifest.csv"
MANIFEST_COLUMNS = [
    "label", "fall", "c_w", "rocket_id", "flight_id", "status", "fehler", "file",
]
MODEL_VERSION = "1"
T_START = 293.15  # Standard des Backends (temp0 wird nicht gesendet)

# Basisrakete in SI-Einheiten wie durchsatz/run.py: plausible Werte, NICHT gemessen.
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,
    "d_nozzle": 0.022,
    "m_empty": 0.15,
    "c_w": 0.345,
    "d_body": 0.09,
}

# Varianten wie im Validierungssatz. R8/R9: Durchmesser als Anhaltswert,
# NICHT gemessen.
CHANGES = {
    "R0": {},
    "R1": {"p0_gauge": 3e5},
    "R2": {"p0_gauge": 7e5},
    "R3": {"v_water0": 0.3e-3},
    "R4": {"v_water0": 0.7e-3},
    "R5": {"d_nozzle": 0.015},
    "R6": {"m_empty": 0.10},
    "R7": {"m_empty": 0.25},
    "R8": {"v_bottle": 1.0e-3, "d_body": 0.079},
    "R9": {"v_bottle": 2.0e-3, "d_body": 0.102},
}

# Fälle der Notiz: F1 ohne Widerstand, F2 mit c_ref (Barrio-Perotti et al. 2009).
CASES = {"F1": 0.0, "F2": 0.345}

# Ergebnisfelder, die die Auswertung braucht (müssen Zahlen sein).
RESULT_FIELDS = ["apogee", "h_burnout", "v_burnout", "water_rest"]
RESULT_STATUSES = ("422",)  # Messergebnis, Messung geht weiter


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge R0 bis R9."""
    return [(label, {**BASE, **change}) for label, change in CHANGES.items()]


def runs():
    """Liste (Kürzel, Fall, Konfiguration): je Rakete F1, dann F2."""
    return [
        (label, case, {**config, "c_w": c_w})
        for label, config in rockets()
        for case, c_w in CASES.items()
    ]


def rocket_payload(label, case, config):
    return {"name": f"Analytisch {label} {case}", **config}


def request(method, path, payload=None, timeout=60):
    """HTTP-Anfrage an die API; liefert (Status, Antwort als Bytes)."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def expect(status, body, wanted, what):
    """Bricht ab, wenn der Status nicht stimmt."""
    if status != wanted:
        raise RuntimeError(f"{what}: HTTP {status} statt {wanted}: {body[:500]!r}")


def wait_for_api(seconds=120):
    """Wartet, bis /api/health über Nginx antwortet."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            status, _ = request("GET", "/health", timeout=5)
            if status == 200:
                return
        except OSError:
            pass  # Nginx oder Backend noch nicht erreichbar
        if time.monotonic() > deadline:
            raise RuntimeError(f"API unter {API_BASE} nach {seconds} s nicht erreichbar")
        time.sleep(2)


def error_text(body):
    """Meldungen einer 422-Antwort als eine Zeile (nur für manifest.csv)."""
    try:
        detail = json.loads(body)["detail"]
        return " | ".join(d["msg"] for d in detail)
    except (ValueError, KeyError, TypeError):
        return body.decode("utf-8", errors="replace")[:500]


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_flight(body, where, rocket_id, config):
    """Prüft Kopf, Konfiguration und Vorhandensein der Ergebnisfelder.

    Die Ergebniswerte selbst werden nicht angesehen; Fehlertexte nennen nur
    Feldnamen, keine Werte.
    """
    flight = json.loads(body)
    if flight.get("rocket_id") != rocket_id:
        raise RuntimeError(f"{where}: Flug gehört nicht zu Rakete {rocket_id}")
    if flight.get("series_id") is not None:
        raise RuntimeError(f"{where}: kein Einzelflug")
    if flight.get("model_version") != MODEL_VERSION:
        raise RuntimeError(f"{where}: Modellversion weicht vom Plan ab")
    for key, value in config.items():
        if flight.get(key) != value:
            raise RuntimeError(f"{where}: Feld {key} weicht von der Eingabe ab")
    if flight.get("temp0") != T_START:
        raise RuntimeError(f"{where}: temp0 ist nicht der Standard")
    for key in RESULT_FIELDS:
        if not is_number(flight.get(key)):
            raise RuntimeError(f"{where}: Feld {key} fehlt")
    if not isinstance(flight.get("id"), int):
        raise RuntimeError(f"{where}: Feld id fehlt")
    return flight["id"]


def run_one(label, case, config):
    """Rakete anlegen und einen Einzelflug rechnen. Liefert (Zeile, JSON oder None)."""
    where = f"{label} {case}"
    status, body = request("POST", "/rockets", rocket_payload(label, case, config))
    expect(status, body, 201, f"{where}: Rakete anlegen")
    rocket_id = json.loads(body)["id"]

    status, body = request("POST", f"/rockets/{rocket_id}/flights")
    row = {
        "label": label, "fall": case, "c_w": repr(config["c_w"]),
        "rocket_id": rocket_id, "flight_id": "", "status": str(status),
        "fehler": "", "file": "",
    }
    if str(status) in RESULT_STATUSES:
        row["fehler"] = error_text(body)
        return row, None
    expect(status, body, 201, f"{where}: Flug rechnen")
    flight_id = check_flight(body, where, rocket_id, config)
    row["flight_id"] = flight_id
    row["file"] = f"{label}_{case}_flug_{flight_id}.json"
    return row, body


def measure():
    """Alle 20 Läufe. Liefert (Manifestzeilen, {Dateiname: JSON})."""
    rows, files = [], {}
    for label, case, config in runs():
        row, body = run_one(label, case, config)
        rows.append(row)
        if body is not None:
            files[row["file"]] = body
        print(f"{label} {case}: Rakete {row['rocket_id']}, "
              f"Flug {row['flight_id'] or '-'}, Status {row['status']}")
    return rows, files


def write_results(rows, files, data_dir):
    """Schreibt die Antworten byteweise unverändert und danach das Manifest."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (data_dir / name).write_bytes(body)
    with open(data_dir / MANIFEST_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(data_dir=DATA_DIR):
    if (data_dir / MANIFEST_NAME).exists():
        print(f"Abbruch: {data_dir / MANIFEST_NAME} existiert bereits (schon gemessen).")
        return 2
    wait_for_api()
    try:
        rows, files = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben; bereits angelegte Raketen/Flüge bleiben in der Datenbank.")
        return 1
    write_results(rows, files, data_dir)
    n_422 = sum(row["status"] in RESULT_STATUSES for row in rows)
    print(f"Fertig: {len(rows)} Läufe in {data_dir / MANIFEST_NAME} "
          f"(davon mit 422: {n_422})")
    return 0


if __name__ == "__main__":
    sys.exit(main())