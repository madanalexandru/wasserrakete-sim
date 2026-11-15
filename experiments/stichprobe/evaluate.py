"""Auswertung der Stichprobe E1 bis E4: S, KPI je Eckrakete, Tabelle, Abbildung.

Plan: docs/validation/stichprobe_plan.md (Abschnitte 2, 3 und 6).

Liest aus data/:
    modell_manifest.csv   Übersicht der Scan-Serien und Modellflüge
    scan_*.csv            c_w-Scan je Eckrakete (für S, e und Re_max)
    modell_*.json         Einzelflug mit c_w' je Eckrakete (für d)
    tool_werte.csv        Läufe im Referenztool
Schreibt nach results/:
    stichprobe.csv              volle Genauigkeit, Punkt als Dezimaltrenner
    stichprobe.md               gerundet, Dezimalkomma, für den Bericht
    abbildung_stichprobe.png    300 dpi
    abbildung_stichprobe.svg    Vektorgrafik
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python stichprobe/evaluate.py"
"""

import bisect
import csv
import json
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"

LABELS = list(run.CORNERS)  # E1 bis E4
ANCHOR = "A0"
CONTROL = "K-E1"
CONTROL_OF = "E1"
NOT_EVALUATED = "nicht ausgewertet"  # Vermerk für Läufe außerhalb des Plans

# Referenzwert und Schwelle wie im c_w-Plan (Abschnitt 7)
C_REF = 0.345
C_FORM_LOW = 0.30  # nähere Grenze des Formbands

# Reynoldszahl: kinematische Viskosität und Gültigkeitsgrenze von c_ref
NU = 1.453e-5
RE_LIMIT = 2e5

# Tool: Hauptpaar, dann Ersatzpaar (Mitte jeweils 0,345); Impulsgrenze in Ns
PAIRS = [(0.33, 0.36), (0.32, 0.37)]
TOL_IMPULSE = 0.05

# Anker A0: Lauf 1 des Tool-Vergleichs R0 bis R9 (= T3b aus dem Funktionstest)
A0_VALUES = {"apogee_m": 49.57, "t_apogee_s": 2.89, "impulse_ns": 14.14, "burn_time_s": 0.06,
             "burnout_t_s": 0.07, "burnout_h_m": 1.87, "burnout_v_mps": 42.76}
VALUE_FIELDS = list(A0_VALUES)

CONFIG_FIELDS = list(next(iter(run.CORNERS.values())))  # ohne c_w

CSV_COLUMNS = [
    "label", "konfiguration", "h_modell_m", "h_tool_m", "d_pct", "S_pct", "kpi_erfuellt",
    "paar", "e_pct", "h_ref_m", "re_max", "re_ueber_grenze",
]


# --- Modellscan --------------------------------------------------------------

def interp(xs, ys, x):
    """Lineare Interpolation; xs aufsteigend. Rasterpunkte werden exakt getroffen."""
    if not xs[0] <= x <= xs[-1]:
        raise ValueError(f"x = {x} außerhalb von [{xs[0]}, {xs[-1]}]")
    i = bisect.bisect_left(xs, x)
    if xs[i] == x:
        return ys[i]
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def scan_metrics(cw, h, v_burnout, d_body):
    """S, h_ref und Re_max aus einem c_w-Scan (gleiche Rechnung wie der c_w-Plan)."""
    h_ref = interp(cw, h, C_REF)
    re_max = interp(cw, v_burnout, C_REF) * d_body / NU
    return {
        "h_ref": h_ref,
        "S_pct": 100 * ((interp(cw, h, C_FORM_LOW) - h_ref) / h_ref),  # Reihenfolge wie c_w-Plan
        "re_max": re_max,
    }


def read_scan_rows(path):
    """CSV-Export einer Serie, nach c_w sortiert."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: float(r["c_w"]))
    return rows


def load_manifest(data_dir):
    with open(data_dir / run.MANIFEST_NAME, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    if [m["label"] for m in manifest] != LABELS:
        raise ValueError("Übersicht nicht vollständig oder in falscher Reihenfolge")
    return manifest


def load_scans(data_dir, manifest):
    """Je Eckrakete: Raster, Apogäen, Kennzahlen; prüft Raster und Konfiguration."""
    wanted_cw = run.expected_cw()
    scans = {}
    for m in manifest:
        label = m["label"]
        rows = read_scan_rows(data_dir / m["scan_file"])
        cw = [float(r["c_w"]) for r in rows]
        if cw != wanted_cw:
            raise ValueError(f"{label}: c_w-Raster weicht vom Plan ab")
        for r in rows:
            if (any(float(r[k]) != run.CORNERS[label][k] for k in CONFIG_FIELDS)
                    or float(r["temp0"]) != run.T_START
                    or r["model_version"] != run.MODEL_VERSION):
                raise ValueError(f"{label}: Scan passt nicht zum Plan")
        h = [float(r["apogee"]) for r in rows]
        v = [float(r["v_burnout"]) for r in rows]
        scans[label] = {"apogee": dict(zip(cw, h)),
                        **scan_metrics(cw, h, v, run.CORNERS[label]["d_body"])}
    return scans


def load_model(data_dir, manifest):
    """Apogäum je Eckrakete aus dem Einzelflug; prüft Konfiguration, c_w', temp0, Version."""
    model = {}
    for m in manifest:
        label = m["label"]
        flight = json.loads((data_dir / m["flight_file"]).read_bytes())
        if (any(flight[k] != run.CORNERS[label][k] for k in CONFIG_FIELDS)
                or flight["c_w"] != run.CW_STRICH or flight["temp0"] != run.T_START
                or flight["model_version"] != run.MODEL_VERSION
                or flight["series_id"] is not None):
            raise ValueError(f"{label}: Flug passt nicht zum Plan")
        model[label] = flight["apogee"]
    return model


# --- Referenztool ------------------------------------------------------------

def num(text):
    """Leeres Feld = keine Anzeige (NaN oder "-") -> None."""
    return float(text) if text.strip() else None


def load_tool(path):
    """Liest tool_werte.csv (LF oder CRLF); unbekannte Labels nur mit Vermerk."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    known = set(LABELS) | {ANCHOR, CONTROL}
    parsed, seen = [], set()
    for r in rows:
        p = {"lauf": int(r["lauf"]), "label": r["label"], "form": r["form"],
             "c_w": float(r["c_w"]), "bemerkung": r["bemerkung"]}
        p.update({k: num(r[k]) for k in VALUE_FIELDS})
        if p["form"] != "std":
            raise ValueError(f"Lauf {p['lauf']}: nur Standardform geplant")
        if p["label"] not in known:
            if NOT_EVALUATED not in p["bemerkung"]:
                raise ValueError(f"Lauf {p['lauf']}: unbekanntes Label ohne Vermerk")
            continue  # Lauf außerhalb des Plans, nicht ausgewertet
        key = (p["label"], p["c_w"])
        if p["label"] in LABELS:
            if key in seen:
                raise ValueError(f"Lauf {p['lauf']}: {key} doppelt")
            seen.add(key)
        parsed.append(p)
    return parsed


def find(rows, label, c_w):
    for r in rows:
        if (r["label"], r["c_w"]) == (label, c_w):
            return r
    return None


def check_controls(rows):
    """A0 muss Lauf 1 des Tool-Vergleichs gleichen, K-E1 den E1-Läufen (beide c_w)."""
    anchors = [r for r in rows if r["label"] == ANCHOR]
    if not anchors:
        raise ValueError("Anker A0 fehlt")
    for r in anchors:
        if any(r[k] != v for k, v in A0_VALUES.items()):
            raise ValueError(f"Lauf {r['lauf']}: Anker weicht ab")
    controls = [r for r in rows if r["label"] == CONTROL]
    if sorted(r["c_w"] for r in controls) != list(PAIRS[0]):
        raise ValueError("Kontrolle K-E1 nicht bei 0,33 und 0,36")
    for r in controls:
        ref = find(rows, CONTROL_OF, r["c_w"])
        if ref is None or any(r[k] != ref[k] for k in VALUE_FIELDS):
            raise ValueError(f"Lauf {r['lauf']}: Kontrolle weicht von E1 ab")


def pair_valid(a, b):
    """Beide Läufe mit Flug, Impulse höchstens TOL_IMPULSE auseinander."""
    if a is None or b is None:
        return False
    if None in (a["apogee_m"], b["apogee_m"], a["impulse_ns"], b["impulse_ns"]):
        return False
    return round(abs(a["impulse_ns"] - b["impulse_ns"]), 6) <= TOL_IMPULSE


def tool_value(rows, label):
    """h_Tool(0,345) als Mittel des ersten gültigen Paars; None = nicht auswertbar."""
    first = PAIRS[0]
    if find(rows, label, first[0]) is None or find(rows, label, first[1]) is None:
        raise ValueError(f"{label}: Hauptpaar fehlt im Protokoll")
    for c1, c2 in PAIRS:
        a, b = find(rows, label, c1), find(rows, label, c2)
        if pair_valid(a, b):
            return {"h": (a["apogee_m"] + b["apogee_m"]) / 2, "pair": (c1, c2)}
    return None


# --- Vergleich ---------------------------------------------------------------

def kpi_met(d_pct, S_pct):
    """KPI erfüllt bei |d| <= S (Grenzfall zählt als erfüllt)."""
    return abs(d_pct) <= S_pct


def config_text(config):
    """Konfiguration in Worten, z. B. '1 l / 79 mm, 7 bar, Düse 22 mm, 100 g, Wasser 0,33 l'."""
    fmt = lambda v: f"{round(v, 6):g}".replace(".", ",")
    return (f"{fmt(config['v_bottle'] * 1e3)} l / {fmt(config['d_body'] * 1e3)} mm, "
            f"{fmt(config['p0_gauge'] / 1e5)} bar, Düse {fmt(config['d_nozzle'] * 1e3)} mm, "
            f"{fmt(config['m_empty'] * 1e3)} g, Wasser {fmt(config['v_water0'] * 1e3)} l")


def compare(tool_rows, model, scans):
    """Ergebnis je Eckrakete (Prozentwerte in %)."""
    results = []
    for label in LABELS:
        tool = tool_value(tool_rows, label)
        s = scans[label]
        r = {"label": label, "konfiguration": config_text(run.CORNERS[label]),
             "h_modell_m": model[label], "tool": tool, "S_pct": s["S_pct"],
             "h_ref_m": s["h_ref"], "re_max": s["re_max"],
             "re_ueber_grenze": s["re_max"] > RE_LIMIT,
             "d_pct": None, "kpi_erfuellt": None, "e_pct": None}
        if tool is not None:
            r["d_pct"] = 100 * (model[label] - tool["h"]) / tool["h"]
            r["kpi_erfuellt"] = kpi_met(r["d_pct"], s["S_pct"])
            c1, c2 = tool["pair"]
            r["e_pct"] = 100 * ((s["apogee"][c1] + s["apogee"][c2]) / 2 - s["h_ref"]) / s["h_ref"]
        results.append(r)
    return results


def summary(results):
    evaluable = [r for r in results if r["kpi_erfuellt"] is not None]
    return {
        "erfuellt": sum(1 for r in evaluable if r["kpi_erfuellt"]),
        "auswertbar": len(evaluable),
        "nicht_auswertbar": [r["label"] for r in results if r["kpi_erfuellt"] is None],
        "re_ueber_grenze": [r["label"] for r in results if r["re_ueber_grenze"]],
    }


# --- Ausgabe -----------------------------------------------------------------

def write_csv(results, path):
    # LF: Git speichert Ergebnisdateien mit LF, so bleibt eine neu erzeugte Datei bytegleich.
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        rep = lambda x: "" if x is None else repr(x)
        for r in results:
            writer.writerow([
                r["label"], r["konfiguration"], rep(r["h_modell_m"]),
                rep(None if r["tool"] is None else r["tool"]["h"]), rep(r["d_pct"]),
                rep(r["S_pct"]),
                "" if r["kpi_erfuellt"] is None else ("ja" if r["kpi_erfuellt"] else "nein"),
                "" if r["tool"] is None else f"{r['tool']['pair'][0]}/{r['tool']['pair'][1]}",
                rep(r["e_pct"]), rep(r["h_ref_m"]), rep(r["re_max"]),
                "ja" if r["re_ueber_grenze"] else "nein",
            ])


def de(x, digits):
    """Zahl mit fester Nachkommazahl und Dezimalkomma; None -> n. a."""
    if x is None:
        return "n. a."
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def de_sci(x):
    """Wissenschaftliche Schreibweise mit drei geltenden Ziffern, z. B. 1,86·10⁵."""
    mantissa, exponent = f"{x:.2e}".split("e")
    return f"{mantissa.replace('.', ',')}·10{str(int(exponent)).translate(SUPERSCRIPT)}"


def write_md(results, path):
    s = summary(results)
    lines = [
        "| Rakete | Konfiguration | h_Modell in m | h_Tool in m | d in % | S in % "
        "| KPI erfüllt | e in % | Re_max |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for r in results:
        kpi = "n. a." if r["kpi_erfuellt"] is None else ("ja" if r["kpi_erfuellt"] else "nein")
        lines.append(
            f"| {r['label']} | {r['konfiguration']} | {de(r['h_modell_m'], 2)} "
            f"| {de(None if r['tool'] is None else r['tool']['h'], 2)} | {de(r['d_pct'], 2)} "
            f"| {de(r['S_pct'], 2)} | {kpi} | {de(r['e_pct'], 3)} | {de_sci(r['re_max'])} |"
        )
    lines += [
        "",
        f"KPI erfüllt: {s['erfuellt']} von {s['auswertbar']} auswertbaren Eckraketen "
        f"(nicht auswertbar: {', '.join(s['nicht_auswertbar']) or 'keine'}). "
        f"Re_max über 2·10⁵: {', '.join(s['re_ueber_grenze']) or 'keine'}.",
        "",
        "d = (h_Modell − h_Tool) / h_Tool; h_Modell: Einzelflug mit c_w' = 0,345 · 1,2039 / 1,225; "
        "h_Tool: Mittel der Standardform bei c_w = 0,33 und 0,36 (Ersatzpaar 0,32/0,37); "
        "S = (h(0,30) − h(0,345)) / h(0,345) aus dem c_w-Scan je Eckrakete; KPI erfüllt bei "
        "|d| ≤ S; e = Interpolationsfehler aus dem Scan; Re_max = v_burnout(0,345) · d_body / ν "
        "mit ν = 1,453·10⁻⁵ m²/s.",
    ]
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(results, out_dir):
    """d je Eckrakete als Balken, ±S als Marken."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    matplotlib.rcParams.update({"svg.hashsalt": "stichprobe", "font.size": 9})
    comma = FuncFormatter(lambda v, _pos: f"{v:g}".replace(".", ",").replace("-", "−"))

    fig, ax = plt.subplots(figsize=(4.7, 3.0))  # ca. 12 cm x 7,6 cm
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
    fig.savefig(out_dir / "abbildung_stichprobe.png", dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / "abbildung_stichprobe.svg", metadata={"Date": None})
    plt.close(fig)


OUTPUTS = ["stichprobe.csv", "stichprobe.md", "abbildung_stichprobe.png",
           "abbildung_stichprobe.svg"]


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR):
    tool_rows = load_tool(data_dir / "tool_werte.csv")
    check_controls(tool_rows)
    manifest = load_manifest(data_dir)
    results = compare(tool_rows, load_model(data_dir, manifest), load_scans(data_dir, manifest))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "stichprobe.csv")
    write_md(results, out_dir / "stichprobe.md")
    plot(results, out_dir)
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())