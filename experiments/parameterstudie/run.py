"""Parameterstudie: Füllstand-Serien für ein Raster aus 54 Raketen über die API.

Vorab-Notiz: docs/validation/parameterstudie_plan.md

Raster aus den Stufen des Validierungssatzes R0 bis R9 (plausible Werte,
NICHT gemessen): Flasche (Volumen mit Durchmesser) x Startdruck x Düse x
Leermasse = 3 x 3 x 2 x 3 = 54 Raketen. Je Rakete eine Vorwärtsserie über
v_water0 von 5 % bis 95 % des Flaschenvolumens in 91 Schritten; Schritt i
(0 bis 90) hat den Füllstand (5 + i) / 100.

Ablauf: Aufwärmlauf (Stufen von R0, 10 Schritte, nicht gewertet), danach ein
Durchgang über alle 54 Raketen in fester Reihenfolge. Jede Serie durchläuft
Rakete anlegen, Serie rechnen, CSV abrufen.

Das Skript gibt bewusst keine Messwerte aus (keine Zeiten, keine Apogäen).
Es prüft nur die Struktur der Exporte (Zeilenzahl, series_id, geplante
Eingabewerte). Ob die Ergebnisspalten endlich sind, bewertet erst die
Auswertung. Geschrieben werden laeufe.csv (eine Zeile je Serie) und alle
Exporte byteweise unverändert, und zwar erst am Ende der Messung.

Antwortet die API auf eine Serie mit 422, ist das ein Messergebnis: Status
und Fehlertext kommen in laeufe.csv, die Messung geht weiter. Bei 504 oder
abgelaufener Wartezeit endet die Messung, weil das Backend danach evtl. noch
weiterrechnet; die Zeilen bis dahin werden geschrieben. Jeder andere Fehler
bricht ohne Schreiben ab.

Zeiten in laeufe.csv: t_client_s ist die Wanduhrzeit um den POST der Serie,
t_lauf_s die Wanduhrzeit aller Aufrufe einer Zeile (Rakete, Serie, CSV).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python parameterstudie/run.py
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
RUNS_NAME = "laeufe.csv"
RUNS_COLUMNS = [
    "label", "rocket_id", "series_id", "n_steps", "status", "fehlertext",
    "t_client_s", "t_lauf_s", "duration_s", "aufrufe", "file",
]

# Basisrakete in SI-Einheiten wie in durchsatz/run.py: plausible Werte,
# NICHT gemessen. c_w = c_ref = 0,345 (Barrio-Perotti et al. 2009).
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,
    "d_nozzle": 0.022,
    "m_empty": 0.15,
    "c_w": 0.345,
    "d_body": 0.09,
}

# Stufen aus dem Validierungssatz (Kürzel, Werte). Durchmesser 79 und 102 mm
# sind Anhaltswerte, NICHT gemessen.
BOTTLES = [  # R8, R0, R9
    ("F10", {"v_bottle": 1.0e-3, "d_body": 0.079}),
    ("F15", {"v_bottle": 1.5e-3, "d_body": 0.09}),
    ("F20", {"v_bottle": 2.0e-3, "d_body": 0.102}),
]
PRESSURES = [("P3", {"p0_gauge": 3e5}), ("P5", {"p0_gauge": 5e5}), ("P7", {"p0_gauge": 7e5})]
NOZZLES = [("D15", {"d_nozzle": 0.015}), ("D22", {"d_nozzle": 0.022})]
MASSES = [("M100", {"m_empty": 0.10}), ("M150", {"m_empty": 0.15}), ("M250", {"m_empty": 0.25})]
WARMUP_LABEL = "F15-P5-D22-M150"  # Stufen von R0

FILL_START = 0.05
FILL_STOP = 0.95
N_STEPS = 91
WARMUP_STEPS = 10

# Eingabespalten des Exports, die je Zeile dem Plan entsprechen müssen.
CONFIG_COLUMNS = ["v_bottle", "p0_gauge", "d_nozzle", "m_empty", "c_w", "d_body"]

SERIES_TIMEOUT_S = 330  # länger als die Wartezeit von Nginx (300 s)
STOP_STATUSES = ("504", "timeout")  # Messergebnis, Messung endet
RESULT_STATUSES = ("422",)  # Messergebnis, Messung geht weiter


class Calls:
    """Zählt die HTTP-Aufrufe an die API (für den Aufwand je Serie)."""

    count = 0


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge: Flasche außen, Masse innen."""
    result = []
    for b_label, bottle in BOTTLES:
        for p_label, pressure in PRESSURES:
            for d_label, nozzle in NOZZLES:
                for m_label, mass in MASSES:
                    label = f"{b_label}-{p_label}-{d_label}-{m_label}"
                    config = {**BASE, **bottle, **pressure, **nozzle, **mass}
                    # Startwert der Serie; die Serie überschreibt v_water0.
                    config["v_water0"] = FILL_START * config["v_bottle"]
                    result.append((label, config))
    return result


def rocket_payload(label, config, suffix=""):
    return {"name": f"Parameterstudie {label}{suffix}", **config}


def series_payload(label, config, n_steps, suffix=""):
    return {
        "name": f"Parameterstudie {label}{suffix}",
        "mode": "forward",
        "param_name": "v_water0",
        "param_start": FILL_START * config["v_bottle"],
        "param_stop": FILL_STOP * config["v_bottle"],
        "n_steps": n_steps,
    }


def expected_water(config, n_steps):
    """Wassermengen der Serie, gleiche Rechnung wie die API (letzter Wert exakt)."""
    start = FILL_START * config["v_bottle"]
    stop = FILL_STOP * config["v_bottle"]
    last = n_steps - 1
    values = [start + (stop - start) * i / last for i in range(last)]
    values.append(stop)
    return values


def request(method, path, payload=None, timeout=60):
    """HTTP-Anfrage an die API; liefert (Status, Antwort als Bytes)."""
    Calls.count += 1
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
    """Wartet, bis /api/health über Nginx antwortet (zählt nicht als Aufruf)."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            status, _ = request("GET", "/health", timeout=5)
            if status == 200:
                Calls.count = 0
                return
        except OSError:
            pass  # Nginx oder Backend noch nicht erreichbar
        if time.monotonic() > deadline:
            raise RuntimeError(f"API unter {API_BASE} nach {seconds} s nicht erreichbar")
        time.sleep(2)


def is_timeout(err):
    """True, wenn die Wartezeit des Clients abgelaufen ist."""
    if isinstance(err, TimeoutError):
        return True
    return isinstance(err, urllib.error.URLError) and isinstance(err.reason, TimeoutError)


def post_series(rocket_id, payload):
    """POST der Serie mit Zeitmessung; liefert (Status als Text, Antwort, Sekunden)."""
    start = time.perf_counter()
    try:
        status, body = request(
            "POST", f"/rockets/{rocket_id}/series", payload, timeout=SERIES_TIMEOUT_S,
        )
        status = str(status)
    except OSError as err:
        if not is_timeout(err):
            raise
        status, body = "timeout", b""
    return status, body, time.perf_counter() - start


def error_text(body):
    """Meldungen einer 422-Antwort als eine Zeile (nur für laeufe.csv)."""
    try:
        detail = json.loads(body)["detail"]
        return " | ".join(d["msg"] for d in detail)
    except (ValueError, KeyError, TypeError):
        return body.decode("utf-8", errors="replace")[:500]


def parse_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))


def check_csv(rows, series_id, config, n_steps):
    """Prüft nur die Struktur des Exports (keine Werte ausgeben, keine Ergebnisse prüfen)."""
    if len(rows) != n_steps:
        raise RuntimeError(f"Serie {series_id}: {len(rows)} Zeilen statt {n_steps}")
    if any(row["series_id"] != str(series_id) for row in rows):
        raise RuntimeError(f"Serie {series_id}: Zeile mit fremder series_id")
    if [float(row["v_water0"]) for row in rows] != expected_water(config, n_steps):
        raise RuntimeError(f"Serie {series_id}: Wassermengen weichen vom Plan ab")
    for col in CONFIG_COLUMNS:
        if any(float(row[col]) != config[col] for row in rows):
            raise RuntimeError(f"Serie {series_id}: Spalte {col} weicht vom Plan ab")


def run_one(label, config, n_steps, suffix=""):
    """Ein Ablauf: Rakete, Serie, CSV. Liefert (Zeile für laeufe.csv, Export oder None)."""
    before = Calls.count
    start = time.perf_counter()
    status, body = request("POST", "/rockets", rocket_payload(label, config, suffix))
    expect(status, body, 201, f"{label}{suffix}: Rakete anlegen")
    rocket_id = json.loads(body)["id"]

    payload = series_payload(label, config, n_steps, suffix)
    status, body, seconds = post_series(rocket_id, payload)
    row = {
        "label": label, "rocket_id": rocket_id, "series_id": "", "n_steps": n_steps,
        "status": status, "fehlertext": "", "t_client_s": repr(seconds),
        "t_lauf_s": "", "duration_s": "", "aufrufe": "", "file": "",
    }
    if status in STOP_STATUSES or status in RESULT_STATUSES:
        if status in RESULT_STATUSES:
            row["fehlertext"] = error_text(body)
        row["t_lauf_s"] = repr(time.perf_counter() - start)
        row["aufrufe"] = Calls.count - before
        return row, None
    expect(int(status), body, 201, f"{label}{suffix}: Serie starten")
    series = json.loads(body)
    row["series_id"] = series["id"]
    row["duration_s"] = repr(series["duration_s"])

    status, csv_body = request("GET", f"/series/{series['id']}/flights.csv")
    expect(status, csv_body, 200, f"{label}{suffix}: CSV abrufen")
    check_csv(parse_csv(csv_body), series["id"], config, n_steps)
    row["t_lauf_s"] = repr(time.perf_counter() - start)
    row["aufrufe"] = Calls.count - before
    row["file"] = f"{label}_serie_{series['id']}.csv"
    return row, csv_body


def measure():
    """Aufwärmlauf und ein Durchgang. Liefert (Zeilen, Exporte, Abbruchgrund oder None)."""
    config = dict(rockets())[WARMUP_LABEL]
    row, _ = run_one(WARMUP_LABEL, config, WARMUP_STEPS, " Aufwaermlauf")
    if row["status"] != "201":
        raise RuntimeError(f"Aufwaermlauf: Status {row['status']}")
    print("Aufwaermlauf fertig (nicht gewertet)")

    rows, exports = [], {}
    plan = rockets()
    for number, (label, config) in enumerate(plan, start=1):
        row, csv_body = run_one(label, config, N_STEPS)
        rows.append(row)
        print(f"{number}/{len(plan)} {label}: Rakete {row['rocket_id']}, "
              f"Serie {row['series_id'] or '-'}, Status {row['status']}")
        if row["status"] in STOP_STATUSES:
            return rows, exports, f"{label}: Status {row['status']}"
        if csv_body is not None:
            exports[row["file"]] = csv_body
    return rows, exports, None


def write_results(rows, exports, data_dir):
    """Schreibt die Exporte byteweise unverändert und danach laeufe.csv."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, body in exports.items():
        (data_dir / name).write_bytes(body)
    with open(data_dir / RUNS_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RUNS_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(data_dir=DATA_DIR):
    if (data_dir / RUNS_NAME).exists():
        print(f"Abbruch: {data_dir / RUNS_NAME} existiert bereits (schon gemessen).")
        print("Fuer einen neuen Lauf den Ordner data/ vorher leeren.")
        return 2
    wait_for_api()
    try:
        rows, exports, stop_reason = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben; angelegte Raketen/Serien bleiben in der Datenbank.")
        return 1
    write_results(rows, exports, data_dir)
    n_422 = sum(row["status"] in RESULT_STATUSES for row in rows)
    if stop_reason:
        print(f"Messung beendet (KPI-relevant): {stop_reason}")
        print(f"Bis dahin {len(rows)} Serien in {data_dir / RUNS_NAME} (davon mit 422: {n_422})")
        return 3
    print(f"Fertig: {len(rows)} Serien in {data_dir / RUNS_NAME} (davon mit 422: {n_422})")
    return 0


if __name__ == "__main__":
    sys.exit(main())