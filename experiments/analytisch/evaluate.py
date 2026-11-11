"""Auswertung analytische Lösung F1/F2 (KPI 95): eps je Rakete und Fall.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitt 1, Nachtrag 5)

Liest data/manifest.csv, die JSON-Antworten aus data/ und die Schwellen S
aus ../cw_sensitivitaet/results/kennzahlen.csv. Schreibt nach results/:
    analytisch.csv   je Rakete und Fall, volle Genauigkeit
    analytisch.md    gerundet, Dezimalkomma, für den Bericht
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Formeln (Abschnitt 1 der Notiz):
    F1: h_ana = h_b + v_b^2 / (2 g)
        (Timmerman & van der Weele 1999, S. 539, Gl. 9)
    F2: h_ana = h_b + m/(2k) * ln(1 + k v_b^2 / (m g))
        (ebd., S. 542, Gl. 33; Umformung von Hand)
        mit m = m_empty + rho_w * water_rest, k = 0,5 rho c_w pi d^2 / 4
    eps = |h_Modell - h_ana| / h_ana; erfüllt, wenn eps in % <= S/100 (S in %).
ln(1 + x) wird mit math.log1p berechnet (mathematisch gleich, genauer bei
kleinem x).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python analytisch/evaluate.py
"""

import csv
import json
import math
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
CW_DIR = HERE.parent / "cw_sensitivitaet"

# Konstanten wie im Modell (Nachtrag 5), unabhängig hier eingetragen.
G = 9.80665  # m/s²
RHO_AIR = 1.225  # kg/m³
RHO_WATER = 1000.0  # kg/m³

CASES = ("F1", "F2")
OUTPUTS = ["analytisch.csv", "analytisch.md"]
COLUMNS = [
    "label", "fall", "c_w", "status", "auswertbar", "grund", "h_burnout_m",
    "v_burnout_ms", "m_kg", "k_kg_m", "h_modell_m", "h_ana_m", "eps_pct", "S_pct",
    "schwelle_pct", "erfuellt",
]


def yes_no(flag):
    return "ja" if flag else "nein"


def mass(m_empty, water_rest):
    """Masse im Freiflug: Leermasse plus Restwasser."""
    return m_empty + RHO_WATER * water_rest


def drag_k(c_w, d_body):
    """k = 0,5 * rho * c_w * A mit A = pi d^2 / 4."""
    return 0.5 * RHO_AIR * c_w * math.pi * d_body**2 / 4


def h_ana_f1(h_b, v_b):
    return h_b + v_b**2 / (2 * G)


def h_ana_f2(h_b, v_b, m, k):
    return h_b + m / (2 * k) * math.log1p(k * v_b**2 / (m * G))


def eps_pct(h_model, h_ana):
    return abs(h_model - h_ana) / h_ana * 100


def load_kennzahlen(cw_dir):
    with open(cw_dir / "results" / "kennzahlen.csv", newline="", encoding="utf-8") as f:
        return {r["label"]: float(r["S_pct"]) for r in csv.DictReader(f)}


def load_manifest(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expected = [(label, case) for label in run.CHANGES for case in CASES]
    if [(r["label"], r["fall"]) for r in rows] != expected:
        raise ValueError("manifest.csv: Raketen/Fälle weichen vom Plan ab")
    return rows


def assess(row, flight, S_pct):
    """Bewertet einen Lauf. flight ist None, wenn kein Flug vorliegt."""
    case = row["fall"]
    out = {
        "label": row["label"], "fall": case, "c_w": float(row["c_w"]),
        "status": row["status"], "auswertbar": False, "grund": "",
        "h_b": None, "v_b": None, "m": None, "k": None, "h_model": None,
        "h_ana": None, "eps": None, "S_pct": S_pct, "schwelle": S_pct / 100,
        "erfuellt": None,
    }
    if row["status"] != "201":
        out["grund"] = f"Status {row['status']}"
        return out
    if flight["c_w"] != run.CASES[case] or float(row["c_w"]) != run.CASES[case]:
        raise ValueError(f"{row['label']} {case}: c_w passt nicht zum Fall")
    h_b, v_b = flight["h_burnout"], flight["v_burnout"]
    out.update(h_b=h_b, v_b=v_b, h_model=flight["apogee"])
    if v_b <= 0:
        out["grund"] = "v_burnout <= 0"
        return out
    if case == "F1":
        out["h_ana"] = h_ana_f1(h_b, v_b)
    else:
        out["m"] = mass(flight["m_empty"], flight["water_rest"])
        out["k"] = drag_k(flight["c_w"], flight["d_body"])
        out["h_ana"] = h_ana_f2(h_b, v_b, out["m"], out["k"])
    out["eps"] = eps_pct(out["h_model"], out["h_ana"])
    out["erfuellt"] = out["eps"] <= out["schwelle"]
    out["auswertbar"] = True
    return out


def evaluate(data_dir, S):
    results = []
    for row in load_manifest(data_dir / run.MANIFEST_NAME):
        if row["label"] not in S:
            raise ValueError(f"{row['label']}: keine Schwelle S in kennzahlen.csv")
        flight = None
        if row["status"] == "201":
            flight = json.loads((data_dir / row["file"]).read_bytes())
        results.append(assess(row, flight, S[row["label"]]))
    return results


def summary(results):
    """Je Fall: (erfüllt, auswertbar, nicht auswertbar)."""
    s = {}
    for case in CASES:
        mine = [r for r in results if r["fall"] == case]
        ok = [r for r in mine if r["auswertbar"]]
        s[case] = (sum(r["erfuellt"] for r in ok), len(ok), len(mine) - len(ok))
    return s


def rep(x):
    return "" if x is None else repr(x)


def write_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for r in results:
            writer.writerow([
                r["label"], r["fall"], repr(r["c_w"]), r["status"], yes_no(r["auswertbar"]),
                r["grund"], rep(r["h_b"]), rep(r["v_b"]), rep(r["m"]), rep(r["k"]),
                rep(r["h_model"]), rep(r["h_ana"]), rep(r["eps"]), repr(r["S_pct"]),
                repr(r["schwelle"]), "" if r["erfuellt"] is None else yes_no(r["erfuellt"]),
            ])


def de_e(x):
    """Zahl in Exponentialschreibweise mit Dezimalkomma; None -> n. a."""
    if x is None:
        return "n. a."
    return f"{x:.2e}".replace(".", ",")


def cell(r):
    if not r["auswertbar"]:
        return f"n. a. ({r['grund']})"
    return f"{de_e(r['eps'])} ({yes_no(r['erfuellt'])})"


def write_md(results, s, path):
    lines = [
        "# Analytische Lösung: Freiflug ab Brennschluss (10 Raketen je Fall)",
        "",
        "eps = |h_Modell - h_ana| / h_ana in %; erfüllt, wenn eps <= S/100.",
        "",
    ]
    for case, text in (("F1", "ohne Widerstand"), ("F2", "mit Widerstand, c_w = 0,345")):
        ok, n, na = s[case]
        lines.append(f"{case} ({text}): {ok} von {n} auswertbaren Raketen erfüllt; "
                     f"nicht auswertbar: {na}.")
    lines += [
        "",
        "| Rakete | eps F1 in % | eps F2 in % | S/100 in % |",
        "|---|---|---|---|",
    ]
    for label in run.CHANGES:
        mine = {r["fall"]: r for r in results if r["label"] == label}
        lines.append(f"| {label} | {cell(mine['F1'])} | {cell(mine['F2'])} | "
                     f"{de_e(mine['F1']['schwelle'])} |")
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR, cw_dir=CW_DIR):
    results = evaluate(data_dir, load_kennzahlen(cw_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "analytisch.csv")
    write_md(results, summary(results), out_dir / "analytisch.md")
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())