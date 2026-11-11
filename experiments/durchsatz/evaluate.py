"""Auswertung Durchsatz vorwärts: Kennzahlen je Rakete, KPI, Monotonie.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitt 2, Nachtrag 1,
Nachtrag 2)

Liest data/zeiten.csv und die CSV-Exporte aus data/ und schreibt nach
results/:
    durchsatz.csv    je Rakete, volle Genauigkeit, Punkt als Dezimaltrenner
    monotonie.csv    je Rakete Ja/Nein (Eingabe für den Algorithmenvergleich)
    durchsatz.md     gerundet, Dezimalkomma, für den Bericht
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python durchsatz/evaluate.py
"""

import csv
import statistics
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"

LABELS = list(run.CHANGES)
N_STEPS = run.SERIES["n_steps"]

# Schwellen aus der Vorab-Notiz, Abschnitt 2
T_MAX_S = 300.0  # t_Client muss kleiner sein (proxy_read_timeout)
CALLS_MAX = 3  # Rakete, Serie, CSV

DURCHSATZ_COLUMNS = [
    "label", "durchgaenge",
    "t_client_median_s", "t_client_min_s", "t_client_max_s",
    "d_client_median", "d_client_min", "d_client_max",
    "d_server_median", "d_server_min", "d_server_max",
    "aufrufe_max", "zeit_erfuellt", "aufwand_erfuellt",
]
MONOTONIE_COLUMNS = ["label", "file", "m1", "m2", "abnahmen", "abnahmen_le0", "im_vergleich"]


def yes_no(flag):
    return "ja" if flag else "nein"


def load_times(path):
    """Liest zeiten.csv und prüft den vollständigen Ablauf (D1-D3 x R0-R9)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != run.TIMES_COLUMNS:
            raise ValueError("zeiten.csv: Spalten weichen von run.py ab")
        raw = list(reader)
    expected = [(p, label) for p in range(1, run.PASSES + 1) for label in LABELS]
    found = [(int(r["durchgang"]), r["label"]) for r in raw]
    if found != expected:
        raise ValueError("zeiten.csv: Zeilen fehlen oder Reihenfolge weicht ab")
    rows = []
    for r in raw:
        where = f"zeiten.csv {r['label']} D{r['durchgang']}"
        if r["status"] != "201":
            raise ValueError(f"{where}: Status {r['status']} (Auswertung setzt 201 voraus)")
        if int(r["n_steps"]) != N_STEPS:
            raise ValueError(f"{where}: n_steps weicht ab")
        t_client, duration = float(r["t_client_s"]), float(r["duration_s"])
        if not (t_client > 0 and duration > 0):
            raise ValueError(f"{where}: Zeit nicht positiv")
        want_file = f"{r['label']}_serie_{r['series_id']}.csv" if r["durchgang"] == "1" else ""
        if r["file"] != want_file:
            raise ValueError(f"{where}: Dateiname weicht ab")
        rows.append({
            "label": r["label"], "durchgang": int(r["durchgang"]),
            "series_id": r["series_id"], "file": r["file"],
            "t_client": t_client, "duration": duration, "aufrufe": int(r["aufrufe"]),
        })
    if len({r["series_id"] for r in rows}) != len(rows):
        raise ValueError("zeiten.csv: series_id doppelt")
    return rows


def load_apogees(path, series_id):
    """Apogäen eines Exports in Reihenfolge der Startdrücke (Struktur geprüft)."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != N_STEPS:
        raise ValueError(f"{path.name}: {len(rows)} Zeilen statt {N_STEPS}")
    if any(r["series_id"] != series_id for r in rows):
        raise ValueError(f"{path.name}: Zeile mit fremder series_id")
    if [float(r["p0_gauge"]) for r in rows] != run.expected_p0(N_STEPS):
        raise ValueError(f"{path.name}: Startdrücke weichen vom Plan ab")
    return [float(r["apogee"]) for r in rows]


def monotonicity(h):
    """M1, M2 und Abnahmen nach Abschnitt 2 und Nachtrag 2 der Vorab-Notiz."""
    pairs = list(zip(h, h[1:]))
    drops = [(a, b) for a, b in pairs if b < a]
    m1 = not drops
    first = next((i for i, x in enumerate(h) if x > 0), None)
    m2 = first is not None and all(b > a for a, b in pairs[first:])
    return {
        "m1": m1, "m2": m2, "abnahmen": len(drops),
        "abnahmen_le0": sum(1 for a, b in drops if a <= 0 and b <= 0),
        "im_vergleich": m2,
    }


def throughput(rows):
    """Kennzahlen je Rakete über alle Durchgänge."""
    results = []
    for label in LABELS:
        mine = [r for r in rows if r["label"] == label]
        t = [r["t_client"] for r in mine]
        dc = [N_STEPS / r["t_client"] for r in mine]
        ds = [N_STEPS / r["duration"] for r in mine]
        calls = [r["aufrufe"] for r in mine]
        results.append({
            "label": label, "durchgaenge": len(mine),
            "t_client": (statistics.median(t), min(t), max(t)),
            "d_client": (statistics.median(dc), min(dc), max(dc)),
            "d_server": (statistics.median(ds), min(ds), max(ds)),
            "aufrufe_max": max(calls),
            "zeit_erfuellt": all(x < T_MAX_S for x in t),
            "aufwand_erfuellt": all(c <= CALLS_MAX for c in calls),
        })
    return results


def summary(rows):
    """KPI über alle Serien (Abschnitt 2: jede Serie in jedem Durchgang)."""
    return {
        "serien": len(rows),
        "zeit_ok": sum(1 for r in rows if r["t_client"] < T_MAX_S),
        "aufwand_ok": sum(1 for r in rows if r["aufrufe"] <= CALLS_MAX),
    }


def write_durchsatz_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(DURCHSATZ_COLUMNS)
        for r in results:
            writer.writerow([
                r["label"], r["durchgaenge"],
                *map(repr, r["t_client"]), *map(repr, r["d_client"]), *map(repr, r["d_server"]),
                r["aufrufe_max"], yes_no(r["zeit_erfuellt"]), yes_no(r["aufwand_erfuellt"]),
            ])


def write_monotonie_csv(mono, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(MONOTONIE_COLUMNS)
        for m in mono:
            writer.writerow([
                m["label"], m["file"], yes_no(m["m1"]), yes_no(m["m2"]),
                m["abnahmen"], m["abnahmen_le0"], yes_no(m["im_vergleich"]),
            ])


def de(x, digits):
    """Zahl mit fester Nachkommazahl und Dezimalkomma."""
    return f"{x:.{digits}f}".replace(".", ",")


def write_md(results, mono, s, path):
    lines = [
        "# Durchsatz vorwärts (1000 Schritte je Serie)",
        "",
        f"KPI Zeit: {s['zeit_ok']} von {s['serien']} Serien mit t_Client < "
        f"{de(T_MAX_S, 0)} s.",
        f"KPI Aufwand: {s['aufwand_ok']} von {s['serien']} Serien mit höchstens "
        f"{CALLS_MAX} Aufrufen.",
        "",
        "Median (Min. bis Max.) über die Durchgänge. D in Flügen/s.",
        "",
        "| Rakete | t_Client in s | D_Client | D_Server | Aufrufe max. | Zeit | Aufwand |",
        "|---|---|---|---|---|---|---|",
    ]
    fmt = lambda v, d: f"{de(v[0], d)} ({de(v[1], d)} bis {de(v[2], d)})"
    for r in results:
        lines.append(
            f"| {r['label']} | {fmt(r['t_client'], 1)} | {fmt(r['d_client'], 1)} | "
            f"{fmt(r['d_server'], 1)} | {r['aufrufe_max']} | {yes_no(r['zeit_erfuellt'])} | "
            f"{yes_no(r['aufwand_erfuellt'])} |"
        )
    lines += [
        "",
        "## Monotonie Apogäum(Startdruck), 1 kPa bis 1000 kPa",
        "",
        "M1: keine Abnahme zwischen Nachbarn. M2: streng steigend ab dem",
        "ersten Apogäum > 0. Ausschluss aus dem Algorithmenvergleich nur bei",
        "M2 = nein (Nachtrag 2).",
        "",
        "| Rakete | M1 | M2 | Abnahmen | davon zwischen Apogäen <= 0 | im Vergleich |",
        "|---|---|---|---|---|---|",
    ]
    for m in mono:
        lines.append(
            f"| {m['label']} | {yes_no(m['m1'])} | {yes_no(m['m2'])} | {m['abnahmen']} | "
            f"{m['abnahmen_le0']} | {yes_no(m['im_vergleich'])} |"
        )
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


OUTPUTS = ["durchsatz.csv", "monotonie.csv", "durchsatz.md"]


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR):
    rows = load_times(data_dir / run.TIMES_NAME)
    mono = []
    for r in rows:
        if r["durchgang"] == 1:
            h = load_apogees(data_dir / r["file"], r["series_id"])
            mono.append({"label": r["label"], "file": r["file"], **monotonicity(h)})
    results = throughput(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_durchsatz_csv(results, out_dir / "durchsatz.csv")
    write_monotonie_csv(mono, out_dir / "monotonie.csv")
    write_md(results, mono, summary(rows), out_dir / "durchsatz.md")
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())