"""Auswertung Wirkung der Ereignissuche: Delta_E (KPI 97 "+"), Delta_W, Delta_A, Auswertungen.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitt 3, Nachtrag 5)

Liest data/werte.csv und die Schwellen S aus
../cw_sensitivitaet/results/kennzahlen.csv. Schreibt nach results/:
    ereignissuche.csv   je Rakete, volle Genauigkeit
    ereignissuche.md    gerundet, Dezimalkomma, für den Bericht
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Regeln:
    Delta_E = (h_V2 - h_V0) / h_V0   Schrittende in beiden Phasen (Kennzahl)
    Delta_W = (h_V3 - h_V0) / h_V0   nur Wasser-Ende am Schrittende (beschreibend)
    Delta_A = (h_V4 - h_V0) / h_V0   nur Apogäum am Schrittende (beschreibend)
    |Delta| in % >= S/100 (S in %) -> "wirksam",
    sonst "für das Apogäum vernachlässigbar".
    Rakete nur auswertbar, wenn V0 bitgleich zu simulate_flight ist.
    Auswertungen je Phase für V0 (binär) und V1 (Interpolation), beschreibend.

Dieses Skript braucht nur die Standardbibliothek (kein Backend).

Start (PowerShell, im Repo-Ordner; eine Zeile):
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python ereignissuche/evaluate.py
"""

import csv
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
CW_DIR = HERE.parent / "cw_sensitivitaet"
VALUES_NAME = "werte.csv"

LABELS = [f"R{i}" for i in range(10)]
VARIANTS = ["V0", "V1", "V2", "V3", "V4"]  # Reihenfolge wie run.VARIANTS
DELTAS = {"E": "V2", "W": "V3", "A": "V4"}  # Kennzahl -> Variante gegen V0
WIRKSAM = "wirksam"
VERNACHLAESSIGBAR = "für das Apogäum vernachlässigbar"

OUTPUTS = ["ereignissuche.csv", "ereignissuche.md"]
COLUMNS = [
    "label", "bitgleich", "auswertbar", "h_V0_m", "h_V2_m", "h_V3_m", "h_V4_m",
    "delta_E_pct", "delta_W_pct", "delta_A_pct", "S_pct", "schwelle_pct",
    "klasse_E", "klasse_W", "klasse_A",
    "eval_wasser_binaer", "eval_freiflug_binaer",
    "eval_wasser_interpolation", "eval_freiflug_interpolation",
    "konv_wasser_interpolation", "konv_freiflug_interpolation",
]


def load_kennzahlen(cw_dir):
    with open(cw_dir / "results" / "kennzahlen.csv", newline="", encoding="utf-8") as f:
        return {r["label"]: float(r["S_pct"]) for r in csv.DictReader(f)}


def load_values(path):
    """Rohwerte als {Rakete: {Variante: Zeile}}; prüft Reihenfolge und Inhalt."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expected = [(label, v) for label in LABELS for v in VARIANTS]
    if [(r["label"], r["variante"]) for r in rows] != expected:
        raise ValueError("werte.csv: Raketen/Varianten weichen vom Plan ab")
    by = {}
    for r in rows:
        if r["variante"] == "V0" and r["bitgleich"] not in ("ja", "nein"):
            raise ValueError(f"{r['label']}: Bitgleich-Feld fehlt")
        if r["variante"] != "V0" and r["bitgleich"] != "":
            raise ValueError(f"{r['label']} {r['variante']}: Bitgleich nur bei V0")
        by.setdefault(r["label"], {})[r["variante"]] = r
    return by


def delta_pct(h, h_ref):
    """Vorzeichenbehaftete relative Abweichung in %."""
    return (h - h_ref) / h_ref * 100


def classify(d_pct, schwelle_pct):
    return WIRKSAM if abs(d_pct) >= schwelle_pct else VERNACHLAESSIGBAR


def evals(row, phase):
    """Auswertungen einer Phase als Zahl; None, wenn es keinen Freiflug gab."""
    if row[f"{phase}_konvergiert"] == "kein Freiflug":
        return None
    return int(row[f"{phase}_auswertungen"])


def assess(label, variants, S_pct):
    v0, v1 = variants["V0"], variants["V1"]
    out = {
        "label": label, "bitgleich": v0["bitgleich"],
        "auswertbar": v0["bitgleich"] == "ja",
        "h": {v: float(variants[v]["apogee"]) for v in ("V0", "V2", "V3", "V4")},
        "delta": {}, "klasse": {}, "S_pct": S_pct, "schwelle": S_pct / 100,
        "eval": {
            ("wasser", "binaer"): evals(v0, "wasser"),
            ("freiflug", "binaer"): evals(v0, "freiflug"),
            ("wasser", "interpolation"): evals(v1, "wasser"),
            ("freiflug", "interpolation"): evals(v1, "freiflug"),
        },
        "konv": {"wasser": v1["wasser_konvergiert"], "freiflug": v1["freiflug_konvergiert"]},
    }
    if out["auswertbar"]:
        for key, variant in DELTAS.items():
            d = delta_pct(out["h"][variant], out["h"]["V0"])
            out["delta"][key] = d
            out["klasse"][key] = classify(d, out["schwelle"])
    return out


def evaluate(data_dir, S):
    by = load_values(data_dir / VALUES_NAME)
    missing = [label for label in LABELS if label not in S]
    if missing:
        raise ValueError(f"keine Schwelle S in kennzahlen.csv für {', '.join(missing)}")
    return [assess(label, by[label], S[label]) for label in LABELS]


def summary(results):
    ok = [r for r in results if r["auswertbar"]]
    s = {"n": len(ok), "na": len(results) - len(ok), "wirksam": {}, "eval": {}, "konv": {}}
    for key in DELTAS:
        s["wirksam"][key] = sum(r["klasse"][key] == WIRKSAM for r in ok)
    for phase in ("wasser", "freiflug"):
        for method in ("binaer", "interpolation"):
            values = [r["eval"][(phase, method)] for r in results
                      if r["eval"][(phase, method)] is not None]
            s["eval"][(phase, method)] = (
                (statistics.median(values), min(values), max(values), sum(values))
                if values else None
            )
        s["konv"][phase] = sum(r["konv"][phase] == "ja" for r in results)
    return s


def rep(x):
    return "" if x is None else repr(x)


def write_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for r in results:
            writer.writerow([
                r["label"], r["bitgleich"], "ja" if r["auswertbar"] else "nein",
                *[repr(r["h"][v]) for v in ("V0", "V2", "V3", "V4")],
                *[rep(r["delta"].get(k)) for k in DELTAS],
                repr(r["S_pct"]), repr(r["schwelle"]),
                *[r["klasse"].get(k, "") for k in DELTAS],
                *[rep(r["eval"][key]) for key in (
                    ("wasser", "binaer"), ("freiflug", "binaer"),
                    ("wasser", "interpolation"), ("freiflug", "interpolation"))],
                r["konv"]["wasser"], r["konv"]["freiflug"],
            ])


def de_e(x):
    """Zahl in Exponentialschreibweise mit Vorzeichen und Dezimalkomma; None -> n. a."""
    if x is None:
        return "n. a."
    return f"{x:+.2e}".replace(".", ",")


def de_e_plain(x):
    return f"{x:.2e}".replace(".", ",")


def de_g(x):
    return f"{x:g}".replace(".", ",")


def write_md(results, s, path):
    lines = [
        "# Wirkung der Ereignissuche (10 Raketen, c_w = 0,345)",
        "",
        "Delta = (h_Variante - h_V0) / h_V0 in %; wirksam, wenn |Delta| >= S/100.",
        f"Auswertbar (V0 bitgleich zu simulate_flight): {s['n']} von {len(results)}; "
        f"nicht auswertbar: {s['na']}.",
        "",
        f"Delta_E (Kennzahl, V2 Schrittende in beiden Phasen): wirksam bei "
        f"{s['wirksam']['E']} von {s['n']} Raketen.",
        f"Delta_W (beschreibend, V3 nur Wasser-Ende): wirksam bei "
        f"{s['wirksam']['W']} von {s['n']} Raketen.",
        f"Delta_A (beschreibend, V4 nur Apogäum): wirksam bei "
        f"{s['wirksam']['A']} von {s['n']} Raketen.",
        "",
        "| Rakete | Delta_E in % | Delta_W in % | Delta_A in % | S/100 in % | Klasse Delta_E |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        klasse = r["klasse"].get("E", "n. a. (V0 nicht bitgleich)")
        lines.append(
            f"| {r['label']} | {de_e(r['delta'].get('E'))} | {de_e(r['delta'].get('W'))} | "
            f"{de_e(r['delta'].get('A'))} | {de_e_plain(r['schwelle'])} | {klasse} |"
        )
    lines += [
        "",
        "## Auswertungen der Ereignissuche je Flug (beschreibend)",
        "",
        "| Phase | binär: Median (Min. bis Max.) | Interpolation: Median (Min. bis Max.) "
        "| Interpolation konvergiert |",
        "|---|---|---|---|",
    ]
    for phase, text in (("wasser", "Wasser-Ende"), ("freiflug", "Apogäum")):
        cells = []
        for method in ("binaer", "interpolation"):
            e = s["eval"][(phase, method)]
            cells.append("n. a." if e is None else f"{de_g(e[0])} ({e[1]} bis {e[2]})")
        lines.append(f"| {text} | {cells[0]} | {cells[1]} | "
                     f"{s['konv'][phase]} von {len(results)} |")
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR, cw_dir=CW_DIR):
    results = evaluate(data_dir, load_kennzahlen(cw_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "ereignissuche.csv")
    write_md(results, summary(results), out_dir / "ereignissuche.md")
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())