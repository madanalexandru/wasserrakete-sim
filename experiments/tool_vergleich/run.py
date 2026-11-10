"""Tool-Vergleich: Modellflüge R0 bis R9 über die API rechnen und speichern.

Plan: docs/validation/tool_vergleich_plan.md, Abschnitt 6.

Je Rakete wird eine neue Rakete mit c_w = c_w' angelegt und ein Einzelflug
gerechnet. Die JSON-Antwort (FlightRead) wird byteweise unverändert in data/
gespeichert, dazu die Übersicht modell_manifest.csv (Kürzel, Raketen-ID,
Flug-ID, Dateiname). Das Skript gibt bewusst keine Apogäen aus und schreibt
erst, wenn alle Flüge erfolgreich waren.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python tool_vergleich/run.py
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
MANIFEST_NAME = "modell_manifest.csv"
MANIFEST_COLUMNS = ["label", "rocket_id", "flight_id", "file"]
MODEL_VERSION = "1"  # Plan, Kopf
T_START = 293.15  # Standard des Backends (temp0 wird nicht gesendet)

# Luftdichte-Angleichung (c_w-Plan, Abschnitt 8): als Formel, nicht gerundet.
CW_STRICH = 0.345 * 1.2039 / 1.225

# Basisrakete wie experiments/cw_sensitivitaet/run.py (SI-Einheiten).
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,
    "d_nozzle": 0.022,
    "m_empty": 0.15,
    "c_w": CW_STRICH,
    "d_body": 0.09,
}

# Varianten: jede ändert nur die genannten Felder der Basis.
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


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge R0 bis R9."""
    return [(label, {**BASE, **change}) for label, change in CHANGES.items()]


def rocket_payload(label, config):
    return {"name": f"Toolvergleich {label}", **config}


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


def check_flight(body, label, rocket_id, config):
    """Prüft nur Kopf und Konfiguration des Flugs, nie das Ergebnis.

    Fehlertexte nennen nur Feldnamen, keine Werte.
    """
    flight = json.loads(body)
    if flight.get("rocket_id") != rocket_id:
        raise RuntimeError(f"{label}: Flug gehört nicht zu Rakete {rocket_id}")
    if flight.get("series_id") is not None:
        raise RuntimeError(f"{label}: kein Einzelflug")
    if flight.get("model_version") != MODEL_VERSION:
        raise RuntimeError(f"{label}: Modellversion weicht vom Plan ab")
    for key, value in config.items():
        if flight.get(key) != value:
            raise RuntimeError(f"{label}: Feld {key} weicht von der Eingabe ab")
    if flight.get("temp0") != T_START:
        raise RuntimeError(f"{label}: temp0 ist nicht der Standard")
    if not isinstance(flight.get("apogee"), (int, float)):
        raise RuntimeError(f"{label}: Feld apogee fehlt")
    if not isinstance(flight.get("id"), int):
        raise RuntimeError(f"{label}: Feld id fehlt")
    return flight["id"]


def measure():
    """Legt alle Raketen an und rechnet je einen Einzelflug."""
    results = []
    for label, config in rockets():
        status, body = request("POST", "/rockets", rocket_payload(label, config))
        expect(status, body, 201, f"{label}: Rakete anlegen")
        rocket_id = json.loads(body)["id"]

        status, body = request("POST", f"/rockets/{rocket_id}/flights")
        expect(status, body, 201, f"{label}: Flug rechnen")
        flight_id = check_flight(body, label, rocket_id, config)

        print(f"{label}: Rakete {rocket_id}, Flug {flight_id}")
        results.append({
            "label": label,
            "rocket_id": rocket_id,
            "flight_id": flight_id,
            "file": f"modell_{label}_flug_{flight_id}.json",
            "json": body,
        })
    return results


def write_results(results, data_dir):
    """Schreibt die Antworten byteweise unverändert und danach die Übersicht."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (data_dir / r["file"]).write_bytes(r["json"])
    with open(data_dir / MANIFEST_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main(data_dir=DATA_DIR):
    if (data_dir / MANIFEST_NAME).exists():
        print(f"Abbruch: {data_dir / MANIFEST_NAME} existiert bereits (schon gemessen).")
        return 2
    wait_for_api()
    try:
        results = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben; bereits angelegte Raketen/Flüge bleiben in der Datenbank.")
        return 1
    write_results(results, data_dir)
    print(f"Fertig: {len(results)} Flüge in {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())