"""Ursachenprüfung: Abweichung Modell - Tool je Flugphase (beschreibend).

Plan: docs/validation/stichprobe_plan.md, Abschnitt 9 (Nachtrag).

Vergleicht für alle Raketen mit Tool-Wert (R0 bis R9 und E1 bis E4) die
Brennschlusswerte (Ende Luftstoß) von Modell und Tool:
    dv_bo    relative Abweichung der Brennschlussgeschwindigkeit in %
    dh_bo    Abweichung der Brennschlusshöhe in m
    d_coast  relative Abweichung von h_bo + v_bo² / (2 g) in % (Steighöhe
             ohne Luftwiderstand, nur zur Zuordnung)
Tool-Werte als Mittel des für h_Tool verwendeten Paars. Keine Schwelle,
kein KPI.

Liest nur committete Daten und Ergebnisse; schreibt nach results/:
    ursache.csv   volle Genauigkeit, Punkt als Dezimaltrenner
    ursache.md    gerundet, Dezimalkomma
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python stichprobe/ursache.py
"""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
TOOL_VERGLEICH = HERE.parent / "tool_vergleich"
G = 9.80665  # wie das Modell und die Tool-Einstellung

CSV_COLUMNS = ["label", "satz", "dv_bo_pct", "dh_bo_m", "d_coast_pct", "d_pct", "S_pct",
               "kpi_erfuellt", "vorzeichen_gleich"]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def coast(h, v):
    """Steighöhe ohne Luftwiderstand ab Brennschluss."""
    return h + v * v / (2 * G)


def tool_burnout(rows, label, pair):
    """Mittel von h_bo und v_bo über das Paar (Standardform)."""
    picked = [r for r in rows if r["label"] == label and r["form"] == "std"
              and float(r["c_w"]) in pair]
    if len(picked) != 2:
        raise ValueError(f"{label}: Paar {pair} nicht eindeutig im Protokoll")
    h = sum(float(r["burnout_h_m"]) for r in picked) / 2
    v = sum(float(r["burnout_v_mps"]) for r in picked) / 2
    return h, v


def row(label, satz, flight, tool_h, tool_v, result):
    """Eine Ergebniszeile (Prozentwerte in %)."""
    d_pct = float(result["d_pct"])
    dv = 100 * (flight["v_burnout"] - tool_v) / tool_v
    return {
        "label": label, "satz": satz,
        "dv_bo_pct": dv,
        "dh_bo_m": flight["h_burnout"] - tool_h,
        "d_coast_pct": 100 * (coast(flight["h_burnout"], flight["v_burnout"])
                              - coast(tool_h, tool_v)) / coast(tool_h, tool_v),
        "d_pct": d_pct, "S_pct": float(result["S_pct"]),
        "kpi_erfuellt": result["kpi_erfuellt"],
        "vorzeichen_gleich": (dv > 0) == (d_pct > 0),
    }


def pair_of(text):
    a, b = text.split("/")
    return (float(a), float(b))


def collect(tool_vergleich=TOOL_VERGLEICH, stichprobe=HERE):
    rows = []
    tv_tool = read_csv(tool_vergleich / "data" / "tool_werte.csv")
    tv_manifest = {m["label"]: m for m in read_csv(tool_vergleich / "data" / "modell_manifest.csv")}
    for r in read_csv(tool_vergleich / "results" / "vergleich.csv"):
        flight = json.loads((tool_vergleich / "data" / tv_manifest[r["label"]]["file"]).read_bytes())
        h, v = tool_burnout(tv_tool, r["label"], pair_of(r["paar_std"]))
        rows.append(row(r["label"], "R0-R9", flight, h, v, r))
    sp_tool = read_csv(stichprobe / "data" / "tool_werte.csv")
    sp_manifest = {m["label"]: m for m in read_csv(stichprobe / "data" / "modell_manifest.csv")}
    for r in read_csv(stichprobe / "results" / "stichprobe.csv"):
        flight = json.loads((stichprobe / "data" / sp_manifest[r["label"]]["flight_file"])
                            .read_bytes())
        h, v = tool_burnout(sp_tool, r["label"], pair_of(r["paar"]))
        rows.append(row(r["label"], "Stichprobe", flight, h, v, r))
    return rows


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CSV_COLUMNS)
        for r in rows:
            w.writerow([r["label"], r["satz"], repr(r["dv_bo_pct"]), repr(r["dh_bo_m"]),
                        repr(r["d_coast_pct"]), repr(r["d_pct"]), repr(r["S_pct"]),
                        r["kpi_erfuellt"], "ja" if r["vorzeichen_gleich"] else "nein"])


def de(x, digits):
    """Dezimalkomma; gerundete Null ohne Vorzeichen (kein "−0,000")."""
    x = round(x, digits) + 0.0
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


def write_md(rows, path):
    same = sum(1 for r in rows if r["vorzeichen_gleich"])
    lines = [
        "| Rakete | Δv_bo in % | Δh_bo in m | d_coast in % | d in % | S in % | KPI erfüllt |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(f"| {r['label']} | {de(r['dv_bo_pct'], 2)} | {de(r['dh_bo_m'], 3)} "
                     f"| {de(r['d_coast_pct'], 2)} | {de(r['d_pct'], 2)} | {de(r['S_pct'], 2)} "
                     f"| {r['kpi_erfuellt']} |")
    lines += [
        "",
        f"Vorzeichen von d gleich dem Vorzeichen von Δv_bo: {same} von {len(rows)} Raketen.",
        "",
        "Δv_bo = (v_bo,Modell − v_bo,Tool) / v_bo,Tool; Δh_bo = h_bo,Modell − h_bo,Tool; "
        "d_coast = relative Abweichung von h_bo + v_bo² / (2 g) (ohne Luftwiderstand, nur zur "
        "Zuordnung); Tool-Werte als Mittel des Paars; Brennschluss = Ende Luftstoß. "
        "Beschreibend, keine Schwelle (Nachtrag Abschnitt 9).",
    ]
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


OUTPUTS = ["ursache.csv", "ursache.md"]


def main(out_dir=RESULTS_DIR, **dirs):
    rows = collect(**dirs)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / "ursache.csv")
    write_md(rows, out_dir / "ursache.md")
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())