"""Beispielrakete mit Nasenkegel und Finnen (R0G): anlegen und fliegen über die API.

Versuchsplan: docs/validation/stabilitaet_plan.md

Legt R0 (ohne Geometrie) und R0G (mit Geometrie, Annahme) an, rechnet je
einen Flug und schreibt die JSON-Antworten unverändert nach data/, dazu
manifest.csv. Geschrieben wird erst, wenn alles erfolgreich war.
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner; der Stack muss laufen):
    docker compose up -d
    docker compose --profile experiment run --rm experiment python stabilitaet/run.py
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
MANIFEST_COLUMNS = ["label", "rocket_id", "flight_id", "rocket_file", "flight_file"]

# R0 wie cw_sensitivitaet/run.py (BASE), c_w = c_ref = 0,345. Plausibel, NICHT gemessen.
R0 = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,
    "d_nozzle": 0.022,
    "m_empty": 0.15,
    "c_w": 0.345,
    "d_body": 0.09,
}

# Geometrie von R0G laut Vorab-Notiz, Abschnitt 2. Alle Werte ANNAHME.
GEOMETRY = {
    "nose_shape": "ogive",
    "l_nose": 0.10,
    "n_fins": 3,
    "fin_root_chord": 0.10,
    "fin_tip_chord": 0.05,
    "fin_span": 0.08,
    "fin_sweep": 0.05,
    "l_total": 0.42,
    "x_fin": 0.32,
    "x_cg_empty": 0.21,
}

STABILITY_FIELDS = ["x_cp", "x_cg_start", "x_cg_empty", "margin_start", "margin_empty"]


def rockets(geometry=None):
    """Liste (Kürzel, Konfiguration): R0 ohne, R0G mit Geometrie."""
    geometry = GEOMETRY if geometry is None else geometry
    return [("R0", dict(R0)), ("R0G", {**R0, **geometry})]


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
    """Bricht ab, wenn der Status nicht stimmt (Fehlertexte enthalten keine Ergebnisse)."""
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
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(f"API unter {API_BASE} nach {seconds} s nicht erreichbar")
        time.sleep(2)


def check_rocket(label, config, rocket):
    """Prüft die Struktur der Antwort, ohne Werte auszugeben."""
    for key, value in config.items():
        if rocket.get(key) != value:
            raise RuntimeError(f"{label}: Feld {key} weicht von der Eingabe ab")
    has_geometry = "nose_shape" in config
    if has_geometry and not isinstance(rocket.get("stability"), dict):
        raise RuntimeError(f"{label}: Stabilitätswerte fehlen")
    if has_geometry and set(rocket["stability"]) != set(STABILITY_FIELDS):
        raise RuntimeError(f"{label}: unerwartete Stabilitätsfelder")
    if not has_geometry and rocket.get("stability") is not None:
        raise RuntimeError(f"{label}: Stabilitätswerte ohne Geometrie")


def check_flight(label, config, rocket_id, flight):
    if flight.get("rocket_id") != rocket_id:
        raise RuntimeError(f"{label}: Flug gehört zu einer anderen Rakete")
    for key, value in config.items():
        if flight.get(key) != value:
            raise RuntimeError(f"{label}: Flug-Feld {key} weicht von der Eingabe ab")
    if not isinstance(flight.get("apogee"), (int, float)):
        raise RuntimeError(f"{label}: Apogäum fehlt")


def measure(geometry=None):
    results = []
    for label, config in rockets(geometry):
        status, body = request("POST", "/rockets", {"name": f"Stabilitaet {label}", **config})
        expect(status, body, 201, f"{label}: Rakete anlegen")
        rocket = json.loads(body)
        check_rocket(label, config, rocket)

        status, fbody = request("POST", f"/rockets/{rocket['id']}/flights")
        expect(status, fbody, 201, f"{label}: Flug rechnen")
        flight = json.loads(fbody)
        check_flight(label, config, rocket["id"], flight)

        print(f"{label}: Rakete {rocket['id']}, Flug {flight['id']}")
        results.append({
            "label": label,
            "rocket_id": rocket["id"],
            "flight_id": flight["id"],
            "rocket_file": f"{label}_rakete.json",
            "flight_file": f"{label}_flug.json",
            "rocket_body": body,
            "flight_body": fbody,
        })
    return results


def write_results(results, data_dir):
    """Schreibt die Antworten byteweise unverändert und danach die Übersicht."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (data_dir / r["rocket_file"]).write_bytes(r["rocket_body"])
        (data_dir / r["flight_file"]).write_bytes(r["flight_body"])
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
    print(f"Fertig: {len(results)} Raketen in {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())