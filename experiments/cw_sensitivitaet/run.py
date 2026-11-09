"""c_w-Sensitivität: Raketen anlegen, Serien über die API rechnen, CSV speichern.

Versuchsplan: docs/validation/cw_sensitivitaet_plan.md

Das Skript gibt bewusst keine Ergebniswerte (Apogäen) aus. Es prüft nur
die Struktur der CSV-Exporte (Zeilenzahl, Serien-ID, c_w-Werte) und
schreibt sie unverändert nach data/, dazu eine Übersicht manifest.csv
(Kürzel, Raketen-ID, Serien-ID, Dateiname). Geschrieben wird erst, wenn
alle Serien erfolgreich waren.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python cw_sensitivitaet/run.py
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
MANIFEST_NAME = "manifest.csv"
MANIFEST_COLUMNS = ["label", "rocket_id", "series_id", "file"]

# Basisrakete in SI-Einheiten: plausible Werte, NICHT gemessen.
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,
    "d_nozzle": 0.022,
    "m_empty": 0.15,
    "c_w": 0.5,  # ohne Bedeutung: jede Serie überschreibt c_w
    "d_body": 0.09,
}

# Varianten: jede ändert nur die genannten Felder der Basis.
# R8/R9: Durchmesser als Anhaltswert, NICHT gemessen.
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

# Eine Vorwärtsserie je Rakete: c_w von 0 bis 1,0 in 101 Werten.
SERIES = {
    "mode": "forward",
    "param_name": "c_w",
    "param_start": 0.0,
    "param_stop": 1.0,
    "n_steps": 101,
}

SERIES_TIMEOUT_S = 330  # etwas länger als die Wartezeit von Nginx (300 s)


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge R0 bis R9."""
    return [(label, {**BASE, **change}) for label, change in CHANGES.items()]


def rocket_payload(label, config):
    return {"name": f"cw-Sensitivitaet {label}", **config}


def series_payload(label):
    return {"name": f"cw-Sensitivitaet {label}", **SERIES}


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


def check_csv(body, series_id):
    """Prüft nur die Struktur des Exports und liefert die Zeilenzahl."""
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))
    wanted = expected_cw()
    if len(rows) != len(wanted):
        raise RuntimeError(f"Serie {series_id}: {len(rows)} Zeilen statt {len(wanted)}")
    if any(row["series_id"] != str(series_id) for row in rows):
        raise RuntimeError(f"Serie {series_id}: Zeile mit fremder series_id")
    if [float(row["c_w"]) for row in rows] != wanted:
        raise RuntimeError(f"Serie {series_id}: c_w-Werte weichen vom Plan ab")
    return len(rows)


def measure():
    """Legt alle Raketen an, rechnet die Serien, holt die CSV-Exporte."""
    results = []
    for label, config in rockets():
        status, body = request("POST", "/rockets", rocket_payload(label, config))
        expect(status, body, 201, f"{label}: Rakete anlegen")
        rocket_id = json.loads(body)["id"]

        status, body = request(
            "POST", f"/rockets/{rocket_id}/series", series_payload(label),
            timeout=SERIES_TIMEOUT_S,
        )
        expect(status, body, 201, f"{label}: Serie starten")
        series_id = json.loads(body)["id"]

        status, body = request("GET", f"/series/{series_id}/flights.csv")
        expect(status, body, 200, f"{label}: CSV abrufen")
        n_rows = check_csv(body, series_id)

        print(f"{label}: Rakete {rocket_id}, Serie {series_id}, {n_rows} Zeilen")
        results.append({
            "label": label,
            "rocket_id": rocket_id,
            "series_id": series_id,
            "file": f"{label}_serie_{series_id}.csv",
            "csv": body,
        })
    return results


def write_results(results, data_dir):
    """Schreibt die Exporte byteweise unverändert und danach die Übersicht."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (data_dir / r["file"]).write_bytes(r["csv"])
    with open(data_dir / MANIFEST_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main(data_dir=DATA_DIR):
    if (data_dir / MANIFEST_NAME).exists():
        print(f"Abbruch: {data_dir / MANIFEST_NAME} existiert bereits (schon gemessen).")
        print("Fuer einen neuen Lauf den Ordner data/ vorher leeren.")
        return 2
    wait_for_api()
    try:
        results = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben; bereits angelegte Raketen/Serien bleiben in der Datenbank.")
        return 1
    write_results(results, data_dir)
    print(f"Fertig: {len(results)} Serien in {data_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())