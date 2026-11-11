"""Durchsatz vorwärts: große Serien über die API rechnen und Zeiten messen.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitt 2, Nachtrag 1)

Ablauf: Aufwärmlauf (R0, 10 Schritte, nicht gewertet), danach 3 Durchgänge
über R0 bis R9. Jeder Durchgang legt neue Raketen an; jede Serie durchläuft
Rakete anlegen, Serie rechnen, CSV abrufen. Gemessen werden die Wanduhrzeit
um den POST der Serie (Client) und duration_s aus der Antwort (Server).

Das Skript gibt bewusst keine Messwerte aus (keine Zeiten, keine Apogäen).
Es prüft nur die Struktur der Exporte und ob alle Durchgänge je Rakete
identische Ergebnisspalten liefern. Geschrieben werden zeiten.csv und je
Rakete der Export des ersten Durchgangs.

Antwortet die API auf eine Serie mit 504 oder läuft die Wartezeit ab, ist
das ein Messergebnis (KPI verfehlt): Die Zeile wird gespeichert und die
Messung endet, weil das Backend danach evtl. noch weiterrechnet.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm experiment python durchsatz/run.py
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
TIMES_NAME = "zeiten.csv"
TIMES_COLUMNS = [
    "label", "durchgang", "rocket_id", "series_id", "n_steps", "status",
    "t_client_s", "duration_s", "aufrufe", "file",
]

# Basisrakete in SI-Einheiten: plausible Werte, NICHT gemessen.
# c_w = c_ref = 0,345 (Barrio-Perotti et al. 2009).
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,  # ohne Bedeutung: jede Serie überschreibt p0_gauge
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

# Größte erlaubte Vorwärtsserie: Startdruck über den Suchbereich des
# inversen Modus (1 kPa bis 1000 kPa Überdruck).
SERIES = {
    "mode": "forward",
    "param_name": "p0_gauge",
    "param_start": 1e3,
    "param_stop": 1e6,
    "n_steps": 1000,
}
WARMUP_STEPS = 10
PASSES = 3

# Ergebnisspalten des CSV-Exports (ohne Flugkurve), für die Gleichheitsprüfung.
RESULT_COLUMNS = [
    "apogee", "t_apogee", "t_water_end", "t_air_end",
    "v_burnout", "h_burnout", "water_rest",
]

SERIES_TIMEOUT_S = 330  # länger als die Wartezeit von Nginx (300 s)
KPI_STATUSES = ("504", "timeout")  # Messergebnis, kein Programmfehler


class Calls:
    """Zählt die HTTP-Aufrufe an die API (für den Aufwand je Serie)."""

    count = 0


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge R0 bis R9."""
    return [(label, {**BASE, **change}) for label, change in CHANGES.items()]


def rocket_payload(label, config, pass_no):
    return {"name": f"Durchsatz {label} D{pass_no}", **config}


def series_payload(label, pass_no, n_steps):
    return {"name": f"Durchsatz {label} D{pass_no}", **SERIES, "n_steps": n_steps}


def expected_p0(n_steps):
    """Startdrücke der Serie, gleiche Rechnung wie die API (letzter Wert exakt)."""
    start, stop = SERIES["param_start"], SERIES["param_stop"]
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


def parse_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode("utf-8"), newline="")))


def check_csv(rows, series_id, n_steps):
    """Prüft nur die Struktur des Exports (keine Werte ausgeben)."""
    if len(rows) != n_steps:
        raise RuntimeError(f"Serie {series_id}: {len(rows)} Zeilen statt {n_steps}")
    if any(row["series_id"] != str(series_id) for row in rows):
        raise RuntimeError(f"Serie {series_id}: Zeile mit fremder series_id")
    if [float(row["p0_gauge"]) for row in rows] != expected_p0(n_steps):
        raise RuntimeError(f"Serie {series_id}: Startdrücke weichen vom Plan ab")
    if any(row[col] == "" for row in rows for col in RESULT_COLUMNS):
        raise RuntimeError(f"Serie {series_id}: leere Ergebnisspalte")


def result_part(rows):
    """Ergebnisspalten als Text (exakter Vergleich ohne Rundung)."""
    return [[row[col] for col in RESULT_COLUMNS] for row in rows]


def run_one(label, config, pass_no, n_steps):
    """Ein vollständiger Ablauf: Rakete, Serie, CSV. Liefert eine Zeitenzeile."""
    before = Calls.count
    status, body = request("POST", "/rockets", rocket_payload(label, config, pass_no))
    expect(status, body, 201, f"{label} D{pass_no}: Rakete anlegen")
    rocket_id = json.loads(body)["id"]

    status, body, seconds = post_series(rocket_id, series_payload(label, pass_no, n_steps))
    row = {
        "label": label, "durchgang": pass_no, "rocket_id": rocket_id,
        "series_id": "", "n_steps": n_steps, "status": status,
        "t_client_s": repr(seconds), "duration_s": "", "aufrufe": "", "file": "",
    }
    if status in KPI_STATUSES:
        row["aufrufe"] = Calls.count - before
        return row, None
    expect(int(status), body, 201, f"{label} D{pass_no}: Serie starten")
    series = json.loads(body)
    row["series_id"] = series["id"]
    row["duration_s"] = repr(series["duration_s"])

    status, csv_body = request("GET", f"/series/{series['id']}/flights.csv")
    expect(status, csv_body, 200, f"{label} D{pass_no}: CSV abrufen")
    rows = parse_csv(csv_body)
    check_csv(rows, series["id"], n_steps)
    row["aufrufe"] = Calls.count - before
    return row, csv_body


def measure():
    """Aufwärmlauf und alle Durchgänge. Liefert (Zeitenzeilen, Exporte, Abbruchgrund)."""
    label, config = rockets()[0]
    run_one(label, config, 0, WARMUP_STEPS)
    print("Aufwaermlauf fertig (nicht gewertet)")

    times, first_csv, results = [], {}, {}
    for pass_no in range(1, PASSES + 1):
        for label, config in rockets():
            row, csv_body = run_one(label, config, pass_no, SERIES["n_steps"])
            times.append(row)
            if csv_body is None:
                return times, first_csv, f"{label} D{pass_no}: Status {row['status']}"
            part = result_part(parse_csv(csv_body))
            if pass_no == 1:
                row["file"] = f"{label}_serie_{row['series_id']}.csv"
                first_csv[row["file"]] = csv_body
                results[label] = part
            elif part != results[label]:
                raise RuntimeError(
                    f"{label} D{pass_no}: Ergebnisspalten weichen von Durchgang 1 ab"
                )
            print(f"{label} D{pass_no}: Rakete {row['rocket_id']}, "
                  f"Serie {row['series_id']}, Status {row['status']}")
    return times, first_csv, None


def write_results(times, first_csv, data_dir):
    """Schreibt die Exporte byteweise unverändert und danach die Zeiten."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, body in first_csv.items():
        (data_dir / name).write_bytes(body)
    with open(data_dir / TIMES_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TIMES_COLUMNS)
        writer.writeheader()
        writer.writerows(times)


def main(data_dir=DATA_DIR):
    if (data_dir / TIMES_NAME).exists():
        print(f"Abbruch: {data_dir / TIMES_NAME} existiert bereits (schon gemessen).")
        print("Fuer einen neuen Lauf den Ordner data/ vorher leeren.")
        return 2
    wait_for_api()
    try:
        times, first_csv, stop_reason = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben; angelegte Raketen/Serien bleiben in der Datenbank.")
        return 1
    write_results(times, first_csv, data_dir)
    if stop_reason:
        print(f"Messung beendet (KPI-relevant): {stop_reason}")
        print(f"Bis dahin gemessene Zeilen in {data_dir / TIMES_NAME}")
        return 3
    print(f"Fertig: {len(times)} Serien in {data_dir / TIMES_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())