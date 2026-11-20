"""Abbildung Genauigkeit: Abweichung d zum Referenztool für R0-R9 und E1-E4.

Liest nur fertige Ergebnisse (keine Rohdaten, keine neue Auswertung):
    ../tool_vergleich/results/vergleich.csv   R0-R9
    ../stichprobe/results/stichprobe.csv      E1-E4
Schreibt nach results/:
    abbildung_genauigkeit.png  300 dpi
    abbildung_genauigkeit.svg  Vektorgrafik

Balken: d in %; Striche: Schwelle ±S. Raketen, die den KPI verfehlen,
sind weiß mit Schraffur und beschriftet (in Graustufen lesbar).
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python genauigkeit/zeichne.py"
"""

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
VERGLEICH = HERE.parent / "tool_vergleich" / "results" / "vergleich.csv"
STICHPROBE = HERE.parent / "stichprobe" / "results" / "stichprobe.csv"
OUTPUTS = ["abbildung_genauigkeit.png", "abbildung_genauigkeit.svg"]
GAP = 1.0  # Lücke zwischen R0-R9 und E1-E4 in Balkenbreiten


def load(path):
    """Liste von Dicts mit label, d (float), S (float), ok (bool)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d, s = float(r["d_pct"]), float(r["S_pct"])
            ok = r["kpi_erfuellt"] == "ja"
            if ok != (abs(d) <= s):
                raise ValueError(f"{path.name}: kpi_erfuellt passt nicht zu d und S bei {r['label']}")
            rows.append({"label": r["label"], "d": d, "S": s, "ok": ok})
    return rows


def positions(n_r, n_e):
    """x-Positionen: erst n_r Raketen, dann eine Lücke, dann n_e Ecken."""
    return [float(i) for i in range(n_r)] + [n_r + GAP + i for i in range(n_e)]


def plot(rows_r, rows_e, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    matplotlib.rcParams.update({"svg.hashsalt": "genauigkeit", "font.size": 9})
    comma = FuncFormatter(lambda v, _pos: f"{v:g}".replace(".", ",").replace("-", "−"))

    rows = rows_r + rows_e
    x = positions(len(rows_r), len(rows_e))
    fig, ax = plt.subplots(figsize=(6.3, 3.4))  # ca. 16 cm x 8,6 cm
    bars = []
    for xi, r in zip(x, rows):
        if r["ok"]:
            b = ax.bar(xi, r["d"], width=0.6, color="0.45", edgecolor="black", linewidth=0.6)
        else:
            b = ax.bar(xi, r["d"], width=0.6, color="white", edgecolor="black", linewidth=0.8, hatch="////")
            ax.annotate(f"{r['label']}: $|d| > S$", (xi, r["d"]), xytext=(0, -4),
                        textcoords="offset points", ha="center", va="top", fontsize=7)
        bars.append(b[0])
    S = [r["S"] for r in rows]
    ax.scatter(x, S, marker="_", s=250, color="black", linewidths=1.2, label="Schwelle ±S")
    ax.scatter(x, [-v for v in S], marker="_", s=250, color="black", linewidths=1.2)
    ax.axhline(0, color="black", linewidth=0.6)
    sep = len(rows_r) - 1 + (1 + GAP) / 2
    ax.axvline(sep, color="black", linewidth=0.6, linestyle="--")
    ax.set_xticks(x, [r["label"] for r in rows])
    ax.set_ylabel(r"Abweichung $d$ in %")
    ax.yaxis.set_major_formatter(comma)
    ax.grid(True, axis="y", linewidth=0.3, color="0.8")
    ax.legend(loc="upper left", fontsize=7, frameon=False)
    ymax = max(S) * 1.15
    ax.set_ylim(-ymax, ymax)
    ax.text((len(rows_r) - 1) / 2, ymax * 0.97, "R0–R9", ha="center", va="top", fontsize=7)
    ax.text(len(rows_r) + GAP + (len(rows_e) - 1) / 2, ymax * 0.97, "Ecken E1–E4",
            ha="center", va="top", fontsize=7)
    fig.tight_layout()
    fig.savefig(out_dir / OUTPUTS[0], dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / OUTPUTS[1], metadata={"Date": None})
    plt.close(fig)
    return x, bars


def main(vergleich=VERGLEICH, stichprobe=STICHPROBE, out_dir=RESULTS_DIR):
    rows_r, rows_e = load(vergleich), load(stichprobe)
    out_dir.mkdir(parents=True, exist_ok=True)
    plot(rows_r, rows_e, out_dir)
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())