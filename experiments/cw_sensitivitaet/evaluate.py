"""Auswertung der c_w-Sensitivität: Kennzahlen je Rakete, Tabelle, Abbildung.

Versuchsplan: docs/validation/cw_sensitivitaet_plan.md (Abschnitte 4, 5, 7, 8)

Liest data/manifest.csv und die CSV-Exporte und schreibt nach results/:
    kennzahlen.csv     volle Genauigkeit, Punkt als Dezimaltrenner
    kennzahlen.md      gerundet, Dezimalkomma, für den Bericht
    abbildung_cw.png   300 dpi (jede Word-Version)
    abbildung_cw.svg   Vektorgrafik (Word aus Microsoft 365)
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python cw_sensitivitaet/evaluate.py"
"""

import bisect
import csv
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"

# Referenzwert und Bänder (Quellen im Versuchsplan, Abschnitt 7)
C_REF = 0.345
FORM_BAND = (0.30, 0.47)
MESS_BAND = (0.341, 0.349)
DELTA_EPS = 0.01  # Schritt für die zentrale Differenz der Elastizität

# Luftdichte: Modell fest, Referenztool aus Rückrechnung (Abschnitt 8)
RHO_MODEL = 1.225
RHO_TOOL = 1.2039

# Reynoldszahl: kinematische Viskosität und Gültigkeitsgrenze von c_ref
NU = 1.453e-5
RE_LIMIT = 2e5

CONFIG_FIELDS = ["v_bottle", "v_water0", "p0_gauge", "d_nozzle", "m_empty", "d_body", "temp0"]

CSV_COLUMNS = [
    "label", "aenderung", "h_ref_m", "S_pct", "delta_form_pct", "delta_mess_pct",
    "eps", "rho_effekt_pct", "cw_strich", "re_max", "re_ueber_grenze",
]


def interp(xs, ys, x):
    """Lineare Interpolation; xs aufsteigend. Rasterpunkte werden exakt getroffen."""
    if not xs[0] <= x <= xs[-1]:
        raise ValueError(f"x = {x} außerhalb von [{xs[0]}, {xs[-1]}]")
    i = bisect.bisect_left(xs, x)
    if xs[i] == x:
        return ys[i]
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def load_series(data_dir):
    """Liest alle Serien laut manifest.csv und prüft Raster und Konfiguration."""
    with open(data_dir / run.MANIFEST_NAME, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    wanted_cw = run.expected_cw()
    series = []
    for m in manifest:
        with open(data_dir / m["file"], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows.sort(key=lambda r: float(r["c_w"]))
        cw = [float(r["c_w"]) for r in rows]
        if cw != wanted_cw:
            raise ValueError(f"{m['label']}: c_w-Raster weicht vom Plan ab")
        configs = {tuple(r[k] for k in CONFIG_FIELDS) for r in rows}
        if len(configs) != 1:
            raise ValueError(f"{m['label']}: Konfiguration ist nicht in allen Zeilen gleich")
        config = {k: float(rows[0][k]) for k in CONFIG_FIELDS}
        series.append({
            "label": m["label"],
            "config": config,
            "cw": cw,
            "h": [float(r["apogee"]) for r in rows],
            "v_burnout": [float(r["v_burnout"]) for r in rows],
        })
    return series


def change_text(config):
    """Beschreibt die Abweichung von der Basisrakete in Worten (für die Tabelle)."""
    parts = []
    base = run.BASE
    fmt = lambda v: f"{v:g}".replace(".", ",")
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


def metrics(s):
    """Kennzahlen einer Rakete nach Versuchsplan (Anteile, nicht Prozent)."""
    cw, h = s["cw"], s["h"]
    hc = lambda c: interp(cw, h, c)
    h_ref = hc(C_REF)
    cw_strich = C_REF * RHO_TOOL / RHO_MODEL
    v_ref = interp(cw, s["v_burnout"], C_REF)
    re_max = v_ref * s["config"]["d_body"] / NU
    return {
        "label": s["label"],
        "aenderung": change_text(s["config"]),
        "h_ref_m": h_ref,
        "S": (hc(FORM_BAND[0]) - h_ref) / h_ref,
        "delta_form": (hc(FORM_BAND[0]) - hc(FORM_BAND[1])) / h_ref,
        "delta_mess": (hc(MESS_BAND[0]) - hc(MESS_BAND[1])) / h_ref,
        "eps": (hc(C_REF + DELTA_EPS) - hc(C_REF - DELTA_EPS)) / (2 * DELTA_EPS) * C_REF / h_ref,
        "rho_effekt": (hc(cw_strich) - h_ref) / h_ref,
        "cw_strich": cw_strich,
        "re_max": re_max,
        "re_ueber_grenze": re_max > RE_LIMIT,
    }


def write_csv(results, path):
    # LF statt CSV-Standard CRLF: Git speichert Ergebnisdateien mit LF, so bleibt
    # eine neu erzeugte Datei byte-gleich mit der Fassung im Repo.
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for r in results:
            writer.writerow([
                r["label"], r["aenderung"], repr(r["h_ref_m"]),
                repr(100 * r["S"]), repr(100 * r["delta_form"]), repr(100 * r["delta_mess"]),
                repr(r["eps"]), repr(100 * r["rho_effekt"]), repr(r["cw_strich"]),
                repr(r["re_max"]), "ja" if r["re_ueber_grenze"] else "nein",
            ])


def de(x, digits):
    """Zahl mit fester Nachkommazahl und Dezimalkomma."""
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def de_sci(x):
    """Wissenschaftliche Schreibweise mit drei geltenden Ziffern, z. B. 1,86·10⁵."""
    mantissa, exponent = f"{x:.2e}".split("e")
    return f"{mantissa.replace('.', ',')}·10{str(int(exponent)).translate(SUPERSCRIPT)}"


def write_md(results, path):
    lines = [
        "| Rakete | Änderung | h(0,345) in m | S in % | Δ Formband in % | Δ Messband in % "
        "| ε | Luftdichte-Effekt in % | Re_max | Re > 2·10⁵ |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['label']} | {r['aenderung']} | {de(r['h_ref_m'], 2)} | {de(100 * r['S'], 2)} "
            f"| {de(100 * r['delta_form'], 2)} | {de(100 * r['delta_mess'], 3)} "
            f"| {de(r['eps'], 3)} | {de(100 * r['rho_effekt'], 2)} | {de_sci(r['re_max'])} "
            f"| {'ja' if r['re_ueber_grenze'] else 'nein'} |"
        )
    lines.append("")
    lines.append(
        "S = (h(0,30) − h(0,345)) / h(0,345); Δ = (h(c_min) − h(c_max)) / h(0,345); "
        "ε bei c_w = 0,345; Luftdichte-Effekt = (h(c_w') − h(0,345)) / h(0,345) mit "
        f"c_w' = 0,345 · {de(RHO_TOOL, 4)} / {de(RHO_MODEL, 3)}; Re_max = v_burnout · d / ν "
        f"bei c_w = 0,345, ν = {de(NU * 1e5, 3)}·10⁻⁵ m²/s."
    )
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(series, results, out_dir):
    """h / h(c_ref) über c_w, eine Kurve je Rakete, beide Bänder grau."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    matplotlib.rcParams.update({"svg.hashsalt": "cw-sensitivitaet", "font.size": 9})
    comma = FuncFormatter(lambda v, _pos: f"{v:g}".replace(".", ",").replace("-", "−"))
    styles = ["-", "--", "-.", ":"]

    fig, ax = plt.subplots(figsize=(6.3, 3.9))  # ca. 16 cm x 10 cm
    ax.axvspan(*FORM_BAND, color="0.85", label="Formband 0,30–0,47")
    ax.axvspan(*MESS_BAND, color="0.55", label="Messband 0,341–0,349")
    ax.axvline(C_REF, color="black", linewidth=0.8, label="c_ref = 0,345")
    for i, (s, r) in enumerate(zip(series, results)):
        ax.plot(s["cw"], [h / r["h_ref_m"] for h in s["h"]], linestyle=styles[i % len(styles)],
                linewidth=1.2, label=s["label"])
    ax.set_xlabel(r"Luftwiderstandsbeiwert $c_w$")
    ax.set_ylabel(r"$h\,/\,h(c_\mathrm{ref})$")
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(comma)
    ax.yaxis.set_major_formatter(comma)
    ax.grid(True, linewidth=0.3, color="0.8")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(out_dir / "abbildung_cw.png", dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / "abbildung_cw.svg", metadata={"Date": None})
    plt.close(fig)


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR):
    series = load_series(data_dir)
    results = [metrics(s) for s in series]
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, out_dir / "kennzahlen.csv")
    write_md(results, out_dir / "kennzahlen.md")
    plot(series, results, out_dir)
    for name in ["kennzahlen.csv", "kennzahlen.md", "abbildung_cw.png", "abbildung_cw.svg"]:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())