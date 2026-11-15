"""Stichprobe Eckpunkte: c_w-Scan und Modellflüge E1 bis E4 über die API.

Plan: docs/validation/stichprobe_plan.md, Abschnitte 1, 2, 3 und 6.

Je Eckrakete zwei neue Raketen:
- "Stichprobe Ex Scan": Vorwärtsserie über c_w von 0 bis 1,0 in 101 Werten,
  CSV-Export byteweise unverändert in data/ (für S, e und Re_max).
- "Stichprobe Ex Flug": c_w = c_w', ein Einzelflug, JSON-Antwort byteweise
  unverändert in data/ (für d).
Dazu die Übersicht modell_manifest.csv. Das Skript gibt bewusst keine
Apogäen aus und schreibt erst, wenn alle Aufrufe erfolgreich waren.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python stichprobe/run.py
"""

import csv
import io
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
MANIFEST_COLUMNS = ["label", "scan_rocket_id", "series_id", "scan_file",
                    "flight_rocket_id", "flight_id", "flight_file"]
MODEL_VERSION = "1"  # Plan, Kopf
T_START = 293.15  # Standard des Backends (temp0 wird nicht gesendet)

# Luftdichte-Angleichung wie im Tool-Vergleich R0 bis R9: als Formel, nicht gerundet.
CW_STRICH = 0.345 * 1.2039 / 1.225
CW_SCAN_ROCKET = 0.5  # ohne Bedeutung: die Serie überschreibt c_w

# Eckraketen in SI-Einheiten (Plan, Abschnitt 1): plausible Werte, NICHT gemessen.
# Durchmesser 79 und 102 mm sind Anhaltswerte, nicht zitierfähig.
CORNERS = {
    "E1": {"v_bottle": 1.0e-3, "v_water0": 0.33e-3, "p0_gauge": 7e5,
           "d_nozzle": 0.022, "m_empty": 0.10, "d_body": 0.079},
    "E2": {"v_bottle": 1.0e-3, "v_water0": 0.33e-3, "p0_gauge": 3e5,
           "d_nozzle": 0.015, "m_empty": 0.25, "d_body": 0.079},
    "E3": {"v_bottle": 2.0e-3, "v_water0": 0.66e-3, "p0_gauge": 7e5,
           "d_nozzle": 0.022, "m_empty": 0.10, "d_body": 0.102},
    "E4": {"v_bottle": 2.0e-3, "v_water0": 0.66e-3, "p0_gauge": 3e5,
           "d_nozzle": 0.015, "m_empty": 0.25, "d_body": 0.102},
}

# Eine Vorwärtsserie je Eckrakete: c_w von 0 bis 1,0 in 101 Werten.
SERIES = {
    "mode": "forward",
    "param_name": "c_w",
    "param_start": 0.0,
    "param_stop": 1.0,
    "n_steps": 101,
}

SERIES_TIMEOUT_S = 330  # etwas länger als die Wartezeit von Nginx (300 s)


def corners():
    """Liste (Kürzel, Konfiguration ohne c_w) in fester Reihenfolge E1 bis E4."""
    return [(label, dict(config)) for label, config in CORNERS.items()]


def scan_payload(label, config):
    return {"name": f"Stichprobe {label} Scan", **config, "c_w": CW_SCAN_ROCKET}


def flight_payload(label, config):
    return {"name": f"Stichprobe {label} Flug", **config, "c_w": CW_STRICH}


def series_payload(label):
    return {"name": f"Stichprobe {label} Scan", **SERIES}


def expected_cw():
    """c_w-Werte der Serie, gleiche Rechnung wie die API (letzter Wert exakt)."""
    start, stop, n = SERIES["param_start"], SERIES["param_stop"], SERIES["n_steps"]
    last = n - 1
    values = [start + (stop - start) * i / last for i in range(last)]
    values.append(stop)
    return values


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
    """Wartet, bis /api/health über Nginx antwortet (Stack startet evtl. gerade)."""
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


def check_csv(body, label, series_id, config):
    """Prüft nur Struktur und Konfiguration des Exports, nie die Ergebnisse.

    Fehlertexte nennen nur Feldnamen, keine Werte.
    """
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))
    wanted = expected_cw()
    if len(rows) != len(wanted):
        raise RuntimeError(f"{label}: Serie mit {len(rows)} Zeilen statt {len(wanted)}")
    for row in rows:
        if row["series_id"] != str(series_id):
            raise RuntimeError(f"{label}: Zeile mit fremder series_id")
        if row["model_version"] != MODEL_VERSION:
            raise RuntimeError(f"{label}: Modellversion weicht vom Plan ab")
        if float(row["temp0"]) != T_START:
            raise RuntimeError(f"{label}: temp0 ist nicht der Standard")
        for key, value in config.items():
            if float(row[key]) != value:
                raise RuntimeError(f"{label}: Feld {key} weicht von der Eingabe ab")
    if [float(row["c_w"]) for row in rows] != wanted:
        raise RuntimeError(f"{label}: c_w-Werte weichen vom Plan ab")
    return len(rows)


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
    for key, value in {**config, "c_w": CW_STRICH}.items():
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
    """Je Eckrakete: Scan-Rakete mit Serie und CSV, Flug-Rakete mit Einzelflug."""
    results = []
    for label, config in corners():
        status, body = request("POST", "/rockets", scan_payload(label, config))
        expect(status, body, 201, f"{label}: Scan-Rakete anlegen")
        scan_rocket_id = json.loads(body)["id"]

        status, body = request(
            "POST", f"/rockets/{scan_rocket_id}/series", series_payload(label),
            timeout=SERIES_TIMEOUT_S,
        )
        expect(status, body, 201, f"{label}: Serie starten")
        series_id = json.loads(body)["id"]

        status, body = request("GET", f"/series/{series_id}/flights.csv")
        expect(status, body, 200, f"{label}: CSV abrufen")
        n_rows = check_csv(body, label, series_id, config)
        scan_csv = body

        status, body = request("POST", "/rockets", flight_payload(label, config))
        expect(status, body, 201, f"{label}: Flug-Rakete anlegen")
        flight_rocket_id = json.loads(body)["id"]

        status, body = request("POST", f"/rockets/{flight_rocket_id}/flights")
        expect(status, body, 201, f"{label}: Flug rechnen")
        flight_id = check_flight(body, label, flight_rocket_id, config)

        print(f"{label}: Serie {series_id} ({n_rows} Zeilen), Flug {flight_id}")
        results.append({
            "label": label,
            "scan_rocket_id": scan_rocket_id,
            "series_id": series_id,
            "scan_file": f"scan_{label}_serie_{series_id}.csv",
            "flight_rocket_id": flight_rocket_id,
            "flight_id": flight_id,
            "flight_file": f"modell_{label}_flug_{flight_id}.json",
            "csv": scan_csv,
            "json": body,
        })
    return results


def write_results(results, data_dir):
    """Schreibt Exporte und Antworten byteweise unverändert, danach die Übersicht."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (data_dir / r["scan_file"]).write_bytes(r["csv"])
        (data_dir / r["flight_file"]).write_bytes(r["json"])
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
        print("Nichts geschrieben; bereits angelegte Raketen/Serien/Flüge bleiben in der Datenbank.")
        return 1
    write_results(results, data_dir)
    print(f"Fertig: {len(results)} Eckraketen in {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())