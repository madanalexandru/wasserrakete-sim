"""Auswertung des Tool-Vergleichs: KPI je Rakete, Tabelle, Abbildung.

Plan: docs/validation/tool_vergleich_plan.md (Abschnitte 3 und 7) und
docs/validation/cw_sensitivitaet_plan.md (Abschnitte 7 und 8).

Liest data/tool_werte.csv, data/modell_manifest.csv mit den Modellflügen,
die Schwellen S aus ../cw_sensitivitaet/results/kennzahlen.csv und den
Modellscan aus ../cw_sensitivitaet/data/. Schreibt nach results/:
    vergleich.csv             volle Genauigkeit, Punkt als Dezimaltrenner
    vergleich.md              gerundet, Dezimalkomma, für den Bericht
    abbildung_vergleich.png   300 dpi
    abbildung_vergleich.svg   Vektorgrafik
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python tool_vergleich/evaluate.py"
"""

import csv
import json
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
CW_DIR = HERE.parent / "cw_sensitivitaet"

LABELS = [f"R{i}" for i in range(10)]
FORMS = ["std", "zyl"]
# Plan, Abschnitt 3: Hauptpaar, dann Ersatzpaar (Mitte jeweils 0,345)
PAIRS = [(0.33, 0.36), (0.32, 0.37)]
TOL_IMPULSE = 0.05  # Ns, Plan, Abschnitt 3

# Anker A0 = T3b aus dem Funktionstest (Plan, Abschnitt 4)
T3B = {"apogee_m": 49.57, "t_apogee_s": 2.89, "impulse_ns": 14.14, "burn_time_s": 0.06,
       "burnout_t_s": 0.07, "burnout_h_m": 1.87, "burnout_v_mps": 42.76}
VALUE_FIELDS = list(T3B)

CSV_COLUMNS = [
    "label", "aenderung", "h_modell_m", "h_tool_m", "d_pct", "S_pct", "kpi_erfuellt",
    "paar_std", "h_tool_zyl_m", "paar_zyl", "delta_form_pct", "form_einordnung", "e_pct",
]


def num(text):
    """Leeres Feld = keine Anzeige (NaN oder "-") -> None."""
    return float(text) if text.strip() else None


def load_tool(path):
    """Liest tool_werte.csv (LF oder CRLF) und prüft Eindeutigkeit."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    parsed, seen = [], set()
    for r in rows:
        p = {"lauf": int(r["lauf"]), "label": r["label"], "form": r["form"],
             "c_w": float(r["c_w"])}
        p.update({k: num(r[k]) for k in VALUE_FIELDS})
        key = (p["label"], p["form"], p["c_w"])
        if p["label"] in LABELS:
            if key in seen:
                raise ValueError(f"Lauf {p['lauf']}: {key} doppelt")
            seen.add(key)
        parsed.append(p)
    return parsed


def check_controls(rows):
    """A0 muss T3b gleichen, K-R0 den ersten R0-Läufen (Plan, Abschnitt 4)."""
    anchors = [r for r in rows if r["label"] == "A0"]
    if not anchors:
        raise ValueError("Anker A0 fehlt")
    for r in anchors:
        if any(r[k] != v for k, v in T3B.items()):
            raise ValueError(f"Lauf {r['lauf']}: Anker weicht von T3b ab")
    controls = [r for r in rows if r["label"] == "K-R0"]
    if not controls:
        raise ValueError("Kontrolle K-R0 fehlt")
    for r in controls:
        ref = find(rows, "R0", r["form"], r["c_w"])
        if ref is None or any(r[k] != ref[k] for k in VALUE_FIELDS):
            raise ValueError(f"Lauf {r['lauf']}: Kontrolle weicht von R0 ab")


def find(rows, label, form, c_w):
    for r in rows:
        if (r["label"], r["form"], r["c_w"]) == (label, form, c_w):
            return r
    return None


def pair_valid(a, b):
    """Beide Läufe mit Flug, Impulse höchstens TOL_IMPULSE auseinander."""
    if a is None or b is None:
        return False
    if None in (a["apogee_m"], b["apogee_m"], a["impulse_ns"], b["impulse_ns"]):
        return False
    return round(abs(a["impulse_ns"] - b["impulse_ns"]), 6) <= TOL_IMPULSE


def tool_value(rows, label, form):
    """h_Tool(0,345) nach Plan, Abschnitt 3; None = nicht auswertbar."""
    first = PAIRS[0]
    if find(rows, label, form, first[0]) is None or find(rows, label, form, first[1]) is None:
        raise ValueError(f"{label} {form}: Hauptpaar fehlt im Protokoll")
    for c1, c2 in PAIRS:
        a, b = find(rows, label, form, c1), find(rows, label, form, c2)
        if pair_valid(a, b):
            return {"h": (a["apogee_m"] + b["apogee_m"]) / 2, "pair": (c1, c2)}
    return None


def load_model(data_dir):
    """Apogäum je Rakete aus den Einzelflügen; prüft c_w', temp0, Version."""
    with open(data_dir / run.MANIFEST_NAME, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    model = {}
    for m in manifest:
        flight = json.loads((data_dir / m["file"]).read_bytes())
        if (flight["c_w"] != run.CW_STRICH or flight["temp0"] != run.T_START
                or flight["model_version"] != run.MODEL_VERSION):
            raise ValueError(f"{m['label']}: Flug passt nicht zum Plan")
        model[m["label"]] = {"apogee": flight["apogee"], "config": flight}
    if sorted(model) != sorted(LABELS):
        raise ValueError("Modellflüge unvollständig")
    return model


def load_kennzahlen(cw_dir):
    with open(cw_dir / "results" / "kennzahlen.csv", newline="", encoding="utf-8") as f:
        return {r["label"]: {"S_pct": float(r["S_pct"]), "h_ref": float(r["h_ref_m"])}
                for r in csv.DictReader(f)}


def load_scan(cw_dir):
    """Modellscan: {Kürzel: {c_w: Apogäum}} an den Rasterpunkten."""
    data = cw_dir / "data"
    with open(data / "manifest.csv", newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    scan = {}
    for m in manifest:
        with open(data / m["file"], newline="", encoding="utf-8") as f:
            scan[m["label"]] = {float(r["c_w"]): float(r["apogee"]) for r in csv.DictReader(f)}
    return scan


def change_text(config):
    """Abweichung von der Basisrakete in Worten (für die Tabelle)."""
    base = run.BASE
    fmt = lambda v: f"{v:g}".replace(".", ",")
    parts = []
    if config["p0_gauge"] != base["p0_gauge"]:
        parts.append(f"Startdruck {fmt(config['p0_gauge'] / 1e5)} bar")
    if config["v_water0"] != base["v_water0"]:
        parts.append(f"Wasser {fmt(round(config['v_water0'] * 1e3, 6))} l")
    if config["d_nozzle"] != base["d_nozzle"]:
        parts.append(f"Düse {fmt(round(config['d_nozzle'] * 1e3, 6))} mm")
    if config["m_empty"] != base["m_empty"]:
        parts.append(f"Leermasse {fmt(round(config['m_empty'] * 1e3, 6))} g")
    if config["v_bottle"] != base["v_bottle"]:
        parts.append(f"Flasche {fmt(round(config['v_bottle'] * 1e3, 6))} l")
    if config["d_body"] != base["d_body"]:
        parts.append(f"Durchmesser {fmt(round(config['d_body'] * 1e3, 6))} mm")
    return ", ".join(parts) if parts else "Basis"


def kpi_met(d_pct, S_pct):
    """KPI erfüllt bei |d| <= S (Grenzfall zählt als erfüllt)."""
    return abs(d_pct) <= S_pct


def compare(tool_rows, model, kennzahlen, scan):
    """Ergebnis je Rakete (Prozentwerte in %)."""
    results = []
    for label in LABELS:
        std = tool_value(tool_rows, label, "std")
        zyl = tool_value(tool_rows, label, "zyl")
        h_model = model[label]["apogee"]
        S = kennzahlen[label]["S_pct"]
        r = {"label": label, "aenderung": change_text(model[label]["config"]),
             "h_modell_m": h_model, "S_pct": S, "std": std, "zyl": zyl,
             "d_pct": None, "kpi_erfuellt": None, "delta_form_pct": None,
             "form_einordnung": None, "e_pct": None}
        if std is not None:
            r["d_pct"] = 100 * (h_model - std["h"]) / std["h"]
            r["kpi_erfuellt"] = kpi_met(r["d_pct"], S)
            c1, c2 = std["pair"]
            h_ref = kennzahlen[label]["h_ref"]
            r["e_pct"] = 100 * ((scan[label][c1] + scan[label][c2]) / 2 - h_ref) / h_ref
        if std is not None and zyl is not None:
            r["delta_form_pct"] = 100 * (zyl["h"] - std["h"]) / std["h"]
            r["form_einordnung"] = "Limitation" if abs(r["delta_form_pct"]) < S else "Kandidat"
        results.append(r)
    return results


def summary(results):
    evaluable = [r for r in results if r["kpi_erfuellt"] is not None]
    return {
        "erfuellt": sum(1 for r in evaluable if r["kpi_erfuellt"]),
        "auswertbar": len(evaluable),
        "kpi_nicht_auswertbar": [r["label"] for r in results if r["kpi_erfuellt"] is None],
        "form_nicht_auswertbar": [r["label"] for r in results if r["delta_form_pct"] is None],
    }


def pair_text(v):
    return "" if v is None else f"{v['pair'][0]}/{v['pair'][1]}"


def write_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        rep = lambda x: "" if x is None else repr(x)
        for r in results:
            writer.writerow([
                r["label"], r["aenderung"], rep(r["h_modell_m"]),
                rep(None if r["std"] is None else r["std"]["h"]), rep(r["d_pct"]),
                rep(r["S_pct"]),
                "" if r["kpi_erfuellt"] is None else ("ja" if r["kpi_erfuellt"] else "nein"),
                pair_text(r["std"]), rep(None if r["zyl"] is None else r["zyl"]["h"]),
                pair_text(r["zyl"]), rep(r["delta_form_pct"]), r["form_einordnung"] or "",
                rep(r["e_pct"]),
            ])


def de(x, digits):
    """Zahl mit fester Nachkommazahl und Dezimalkomma; None -> n. a."""
    if x is None:
        return "n. a."
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


def write_md(results, path):
    s = summary(results)
    lines = [
        "| Rakete | Änderung | h_Modell in m | h_Tool in m | d in % | S in % | KPI erfüllt "
        "| Δ_Form in % | Einordnung | e in % |",
        "|---|---|---:|---:|---:|---:|---|---:|---|---:|",
    ]
    for r in results:
        kpi = "n. a." if r["kpi_erfuellt"] is None else ("ja" if r["kpi_erfuellt"] else "nein")
        lines.append(
            f"| {r['label']} | {r['aenderung']} | {de(r['h_modell_m'], 2)} "
            f"| {de(None if r['std'] is None else r['std']['h'], 2)} | {de(r['d_pct'], 2)} "
            f"| {de(r['S_pct'], 2)} | {kpi} | {de(r['delta_form_pct'], 2)} "
            f"| {r['form_einordnung'] or 'n. a.'} | {de(r['e_pct'], 3)} |"
        )
    lines += [
        "",
        f"KPI erfüllt: {s['erfuellt']} von {s['auswertbar']} auswertbaren Raketen "
        f"(nicht auswertbar: {', '.join(s['kpi_nicht_auswertbar']) or 'keine'}). "
        f"Δ_Form nicht auswertbar: {', '.join(s['form_nicht_auswertbar']) or 'keine'}.",
        "",
        "d = (h_Modell − h_Tool) / h_Tool; h_Modell: Einzelflug mit c_w' = 0,345 · 1,2039 / 1,225; "
        "h_Tool: Mittel der Standardform bei c_w = 0,33 und 0,36 (Ersatzpaar 0,32/0,37); "
        "KPI erfüllt bei |d| ≤ S; Δ_Form = (h_zyl − h_Std) / h_Std, Limitation bei |Δ_Form| < S; "
        "e = Interpolationsfehler aus dem Modellscan.",
    ]
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(results, out_dir):
    """d je Rakete als Balken, ±S als Marken."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    matplotlib.rcParams.update({"svg.hashsalt": "tool-vergleich", "font.size": 9})
    comma = FuncFormatter(lambda v, _pos: f"{v:g}".replace(".", ",").replace("-", "−"))

    fig, ax = plt.subplots(figsize=(6.3, 3.4))  # ca. 16 cm x 8,6 cm
    x = list(range(len(results)))
    for i, r in enumerate(results):
        if r["d_pct"] is None:
            ax.text(i, 0, "n. a.", ha="center", va="bottom", fontsize=7)
        else:
            ax.bar(i, r["d_pct"], width=0.6, color="0.45" if r["kpi_erfuellt"] else "0.8",
                   edgecolor="black", linewidth=0.6)
    S = [r["S_pct"] for r in results]
    ax.scatter(x, S, marker="_", s=250, color="black", linewidths=1.2, label="Schwelle ±S")
    ax.scatter(x, [-v for v in S], marker="_", s=250, color="black", linewidths=1.2)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xticks(x, [r["label"] for r in results])
    ax.set_ylabel(r"Abweichung $d$ in %")
    ax.yaxis.set_major_formatter(comma)
    ax.grid(True, axis="y", linewidth=0.3, color="0.8")
    ax.legend(loc="upper right", fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(out_dir / "abbildung_vergleich.png", dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / "abbildung_vergleich.svg", metadata={"Date": None})
    plt.close(fig)


OUTPUTS = ["vergleich.csv", "vergleich.md", "abbildung_vergleich.png", "abbildung_vergleich.svg"]


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR, cw_dir=CW_DIR):
    tool_rows = load_tool(data_dir / "tool_werte.csv")
    check_controls(tool_rows)
    results = compare(tool_rows, load_model(data_dir), load_kennzahlen(cw_dir), load_scan(cw_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "vergleich.csv")
    write_md(results, out_dir / "vergleich.md")
    plot(results, out_dir)
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())