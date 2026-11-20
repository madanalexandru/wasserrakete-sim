"""Auswertung Exponent: Δβ je Rakete und β, Vergleich mit S (beschreibend).

Plan: docs/validation/exponent_plan.md (Abschnitt 5)

Liest data/werte.csv und S aus tool_vergleich/results/vergleich.csv und
stichprobe/results/stichprobe.csv. Schreibt nach results/:
    exponent.csv  volle Genauigkeit, Punkt als Dezimaltrenner
    exponent.md   gerundet, Dezimalkomma, für den Bericht
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python exponent/evaluate.py
"""

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
OUTPUTS = ["exponent.csv", "exponent.md"]
CONTROL_BETA = 1.4
REFERENCES = [
    ROOT / "tool_vergleich" / "results" / "vergleich.csv",
    ROOT / "stichprobe" / "results" / "stichprobe.csv",
]
LABELS = [f"R{i}" for i in range(10)] + [f"E{i}" for i in range(1, 5)]


def load_values(path):
    """{(Kürzel, β): Apogäum}."""
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["label"], float(r["beta"])): float(r["apogee_m"]) for r in csv.DictReader(f)}


def load_thresholds(paths=REFERENCES):
    S = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                S[r["label"]] = float(r["S_pct"])
    return S


def evaluate(values, S):
    betas = sorted({b for (_, b) in values if b != CONTROL_BETA})
    labels = [l for l in LABELS if (l, CONTROL_BETA) in values]
    if labels != LABELS:
        raise ValueError("werte.csv muss R0-R9 und E1-E4 enthalten")
    rows = []
    for label in labels:
        h0 = values[(label, CONTROL_BETA)]
        for beta in betas:
            d = (values[(label, beta)] - h0) / h0 * 100
            rows.append({"label": label, "beta": beta, "delta_pct": d,
                         "S_pct": S[label], "ueber_S": abs(d) > S[label]})
    summary = []
    for beta in betas:
        sel = [r for r in rows if r["beta"] == beta]
        summary.append({"beta": beta,
                        "min": min(r["delta_pct"] for r in sel),
                        "max": max(r["delta_pct"] for r in sel),
                        "n_ueber_S": sum(r["ueber_S"] for r in sel),
                        "n": len(sel)})
    return rows, summary


def de(x, digits):
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["label", "beta", "delta_pct", "S_pct", "ueber_S"])
        for r in rows:
            w.writerow([r["label"], repr(r["beta"]), repr(r["delta_pct"]), repr(r["S_pct"]),
                        "ja" if r["ueber_S"] else "nein"])


def write_md(rows, summary, path):
    betas = [s["beta"] for s in summary]
    lines = [
        "# Wirkung des Expansionsexponenten β auf das Apogäum (beschreibend)",
        "",
        "Δβ = (h(β) − h(1,4)) / h(1,4); nur Wasserphase, Luftstoß mit 1,4.",
        "Plan: docs/validation/exponent_plan.md. Kein KPI.",
        "",
        "| β | Δβ min | Δβ max | Raketen mit abs(Δβ) > S |",
        "|---|---|---|---|",
    ]
    for s in summary:
        lines.append(f"| {de(s['beta'], 2)} | {de(s['min'], 2)} % | {de(s['max'], 2)} % "
                     f"| {s['n_ueber_S']} von {s['n']} |")
    head = " | ".join(f"Δβ bei {de(b, 2)}" for b in betas)
    lines += ["", f"| Rakete | S | {head} |", "|---" * (2 + len(betas)) + "|"]
    for label in LABELS:
        sel = {r["beta"]: r for r in rows if r["label"] == label}
        cells = " | ".join(f"{de(sel[b]['delta_pct'], 2)} %" for b in betas)
        lines.append(f"| {label} | {de(sel[betas[0]]['S_pct'], 2)} % | {cells} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR, references=REFERENCES):
    rows, summary = evaluate(load_values(data_dir / "werte.csv"), load_thresholds(references))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / OUTPUTS[0])
    write_md(rows, summary, out_dir / OUTPUTS[1])
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())