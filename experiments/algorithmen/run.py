"""Algorithmenvergleich: inverse Serien je Rakete und Suchverfahren über die API.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitte 2 und 3,
Nachtrag 1 bis 3)

Ablauf: Aufwärmlauf (R0, binary, 2 Zielhöhen, nicht gewertet), danach ein
Durchgang R0 bis R9, je Rakete binary, exponential, interpolation. Jede Serie
legt eine neue Rakete an und durchläuft Rakete anlegen, Serie rechnen, CSV
abrufen. Die 40 Zielhöhen reichen von 5 % bis 95 % von h(P_MAX), dem Apogäum
der letzten Zeile des Vorwärts-Exports (1000 kPa). Raketen mit
im_vergleich = nein in durchsatz/results/monotonie.csv werden übersprungen.

Das Skript gibt bewusst keine Messwerte aus (keine Zeiten, Apogäen,
Zielhöhen oder Auswertungszahlen). Geschrieben werden zeiten.csv und alle
Exporte unverändert.

Antwortet die API auf eine Serie mit 422 (Suche nicht konvergiert), ist das
ein Messergebnis: Status und Fehlertext kommen in zeiten.csv, die Messung
geht mit der nächsten Serie weiter. Bei 504 oder abgelaufener Wartezeit endet
die Messung, weil das Backend danach evtl. noch weiterrechnet.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python algorithmen/run.py
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
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DURCHSATZ_DIR = HERE.parent / "durchsatz"
TIMES_NAME = "zeiten.csv"
TIMES_COLUMNS = [
    "label", "searcher", "rocket_id", "series_id", "n_steps", "status",
    "t_client_s", "duration_s", "aufrufe", "file", "fehler",
]

# Basisrakete in SI-Einheiten: plausible Werte, NICHT gemessen.
# c_w = c_ref = 0,345 (Barrio-Perotti et al. 2009).
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,  # ohne Bedeutung: die Suche ersetzt p0_gauge
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

SEARCHERS = ["binary", "exponential", "interpolation"]
N_TARGETS = 40
TARGET_LOW, TARGET_HIGH = 0.05, 0.95  # Anteile von h(P_MAX)
WARMUP_TARGETS = 2
P_MAX = 1e6  # Pa, letzter Startdruck der Vorwärtsserie
FORWARD_STEPS = 1000

SERIES_TIMEOUT_S = 330  # länger als die Wartezeit von Nginx (300 s)
KPI_STATUSES = ("504", "timeout")  # Messergebnis, Messung endet
RESULT_STATUSES = ("422",)  # Messergebnis für K1, Messung geht weiter

# Spalten des Exports, die gefüllt sein müssen
FILLED_COLUMNS = ["p0_gauge", "apogee", "target_apogee", "searcher", "search_evaluations"]


class Calls:
    """Zählt die HTTP-Aufrufe an die API (für den Aufwand je Serie)."""

    count = 0


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge R0 bis R9."""
    return [(label, {**BASE, **change}) for label, change in CHANGES.items()]


def load_monotonie(path):
    """Kürzel -> (im Vergleich ja/nein, Dateiname des Vorwärts-Exports)."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if [r["label"] for r in rows] != list(CHANGES):
        raise ValueError(f"{path.name}: Raketen fehlen oder Reihenfolge weicht ab")
    result = {}
    for r in rows:
        if r["im_vergleich"] not in ("ja", "nein"):
            raise ValueError(f"{path.name}: {r['label']} im_vergleich ungültig")
        result[r["label"]] = (r["im_vergleich"] == "ja", r["file"])
    return result


def load_h_pmax(path):
    """Apogäum der letzten Zeile eines Vorwärts-Exports (Startdruck P_MAX)."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != FORWARD_STEPS:
        raise ValueError(f"{path.name}: Zeilenzahl weicht ab")
    if float(rows[-1]["p0_gauge"]) != P_MAX:
        raise ValueError(f"{path.name}: letzte Zeile nicht bei P_MAX")
    h = float(rows[-1]["apogee"])
    if not h > 0:
        raise ValueError(f"{path.name}: Apogäum bei P_MAX nicht positiv")
    return h


def load_inputs(durchsatz_dir):
    """Kürzel -> h(P_MAX) für alle Raketen im Vergleich (feste Reihenfolge)."""
    mono = load_monotonie(durchsatz_dir / "results" / "monotonie.csv")
    return {
        label: load_h_pmax(durchsatz_dir / "data" / file)
        for label, (included, file) in mono.items()
        if included
    }


def target_range(h_pmax):
    return TARGET_LOW * h_pmax, TARGET_HIGH * h_pmax


def expected_targets(start, stop, n_steps):
    """Zielhöhen der Serie, gleiche Rechnung wie die API (letzter Wert exakt)."""
    last = n_steps - 1
    values = [start + (stop - start) * i / last for i in range(last)]
    values.append(stop)
    return values


def name(label, searcher):
    return f"Algorithmen {label} {searcher}"


def rocket_payload(label, config, searcher):
    return {"name": name(label, searcher), **config}


def series_payload(label, searcher, start, stop, n_steps):
    return {
        "name": name(label, searcher), "mode": "inverse", "param_name": "target_apogee",
        "param_start": start, "param_stop": stop, "n_steps": n_steps, "searcher": searcher,
    }


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
    """Bricht ab, wenn der Status nicht stimmt (Text nur für Programmfehler)."""
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
    """Meldungen einer 422-Antwort als eine Zeile (nur für zeiten.csv)."""
    try:
        detail = json.loads(body)["detail"]
        return " | ".join(d["msg"] for d in detail)
    except (ValueError, KeyError, TypeError):
        return body.decode("utf-8", errors="replace")[:500]


def parse_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))


def check_csv(rows, series_id, searcher, targets):
    """Prüft nur die Struktur des Exports (keine Werte ausgeben)."""
    if len(rows) != len(targets):
        raise RuntimeError(f"Serie {series_id}: {len(rows)} Zeilen statt {len(targets)}")
    if any(row["series_id"] != str(series_id) for row in rows):
        raise RuntimeError(f"Serie {series_id}: Zeile mit fremder series_id")
    if any(row["searcher"] != searcher for row in rows):
        raise RuntimeError(f"Serie {series_id}: Suchverfahren weicht ab")
    if [float(row["target_apogee"]) for row in rows] != targets:
        raise RuntimeError(f"Serie {series_id}: Zielhöhen weichen vom Plan ab")
    if any(row[col] == "" for row in rows for col in FILLED_COLUMNS):
        raise RuntimeError(f"Serie {series_id}: leere Ergebnisspalte")


def run_one(label, config, searcher, h_pmax, n_steps):
    """Ein Ablauf: Rakete, Serie, CSV. Liefert (Zeitenzeile, Export oder None)."""
    before = Calls.count
    where = f"{label} {searcher}"
    status, body = request("POST", "/rockets", rocket_payload(label, config, searcher))
    expect(status, body, 201, f"{where}: Rakete anlegen")
    rocket_id = json.loads(body)["id"]

    start, stop = target_range(h_pmax)
    payload = series_payload(label, searcher, start, stop, n_steps)
    status, body, seconds = post_series(rocket_id, payload)
    row = {
        "label": label, "searcher": searcher, "rocket_id": rocket_id, "series_id": "",
        "n_steps": n_steps, "status": status, "t_client_s": repr(seconds),
        "duration_s": "", "aufrufe": "", "file": "", "fehler": "",
    }
    if status in KPI_STATUSES or status in RESULT_STATUSES:
        if status in RESULT_STATUSES:
            row["fehler"] = error_text(body)
        row["aufrufe"] = Calls.count - before
        return row, None
    expect(int(status), body, 201, f"{where}: Serie starten")
    series = json.loads(body)
    row["series_id"] = series["id"]
    row["duration_s"] = repr(series["duration_s"])

    status, csv_body = request("GET", f"/series/{series['id']}/flights.csv")
    expect(status, csv_body, 200, f"{where}: CSV abrufen")
    check_csv(parse_csv(csv_body), series["id"], searcher,
              expected_targets(start, stop, n_steps))
    row["aufrufe"] = Calls.count - before
    row["file"] = f"{label}_{searcher}_serie_{series['id']}.csv"
    return row, csv_body


def measure(h_pmax):
    """Aufwärmlauf und ein Durchgang. Liefert (Zeitenzeilen, Exporte, Abbruchgrund)."""
    configs = dict(rockets())
    if "R0" not in h_pmax:
        raise RuntimeError("Aufwaermlauf: R0 nicht im Vergleich")
    row, _ = run_one("R0", configs["R0"], "binary", h_pmax["R0"], WARMUP_TARGETS)
    if row["status"] != "201":
        raise RuntimeError(f"Aufwaermlauf: Status {row['status']}")
    print("Aufwaermlauf fertig (nicht gewertet)")

    times, exports = [], {}
    for label in h_pmax:
        for searcher in SEARCHERS:
            row, csv_body = run_one(label, configs[label], searcher, h_pmax[label], N_TARGETS)
            times.append(row)
            print(f"{label} {searcher}: Rakete {row['rocket_id']}, "
                  f"Serie {row['series_id'] or '-'}, Status {row['status']}")
            if row["status"] in KPI_STATUSES:
                return times, exports, f"{label} {searcher}: Status {row['status']}"
            if csv_body is not None:
                exports[row["file"]] = csv_body
    return times, exports, None


def write_results(times, exports, data_dir):
    """Schreibt die Exporte byteweise unverändert und danach die Zeiten."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for file_name, body in exports.items():
        (data_dir / file_name).write_bytes(body)
    with open(data_dir / TIMES_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TIMES_COLUMNS)
        writer.writeheader()
        writer.writerows(times)


def main(data_dir=DATA_DIR, durchsatz_dir=DURCHSATZ_DIR):
    if (data_dir / TIMES_NAME).exists():
        print(f"Abbruch: {data_dir / TIMES_NAME} existiert bereits (schon gemessen).")
        print("Fuer einen neuen Lauf den Ordner data/ vorher leeren.")
        return 2
    try:
        h_pmax = load_inputs(durchsatz_dir)
    except (OSError, ValueError, KeyError) as err:
        print(f"Abbruch: Eingaben aus durchsatz/ fehlerhaft: {err}")
        return 1
    wait_for_api()
    try:
        times, exports, stop_reason = measure(h_pmax)
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben; angelegte Raketen/Serien bleiben in der Datenbank.")
        return 1
    write_results(times, exports, data_dir)
    if stop_reason:
        print(f"Messung beendet (KPI-relevant): {stop_reason}")
        print(f"Bis dahin gemessene Zeilen in {data_dir / TIMES_NAME}")
        return 3
    print(f"Fertig: {len(times)} Serien in {data_dir / TIMES_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())