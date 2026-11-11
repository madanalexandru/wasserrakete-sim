"""Auswertung Parameterstudie: KPI Konfigurationsbandbreite und beschreibende Werte.

Vorab-Notiz: docs/validation/parameterstudie_plan.md (Abschnitte 2 bis 5)

Liest data/laeufe.csv und die Exporte aus data/. Schreibt nach results/:
    parameterstudie.csv          je Rakete, volle Genauigkeit
    parameterstudie.md           gerundet, Dezimalkomma, für den Bericht
    abbildung_fuellstand.png     300 dpi
    abbildung_fuellstand.svg     Vektorgrafik
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

KPI: Abdeckung A = gültige Punkte / (54 x 91). Gültig ist ein Punkt, wenn
seine Serie Status 201 hat und alle 7 Ergebnisspalten endlich sind (leer,
nicht lesbar, NaN oder unendlich = nicht gültig). Ein Apogäum <= 0 ist
gültig und wird getrennt gezählt. Serien mit 422, 504 oder Timeout und
nicht gemessene Raketen zählen mit allen 91 Punkten als nicht gültig.
Erfüllt nur bei A = 100 %.

Beschreibend je Rakete: Füllstand des größten Apogäums f_max unter den
gültigen Punkten (bei Gleichstand der kleinste), "innen", wenn f_max weder
5 % noch 95 % ist, größtes Apogäum, Anzahl Apogäen <= 0. Gesamt: Summen der
Zeiten und Aufrufe sowie Flüge je Sekunde über die Summe von t_lauf_s.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python parameterstudie/evaluate.py"
"""

import csv
import math
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"

# Ergebnisspalten des Exports (wie durchsatz/run.py)
RESULT_COLUMNS = [
    "apogee", "t_apogee", "t_water_end", "t_air_end",
    "v_burnout", "h_burnout", "water_rest",
]
ALL_STATUSES = ("201",) + run.RESULT_STATUSES + run.STOP_STATUSES
N_POINTS = len(run.rockets()) * run.N_STEPS
FIGURE_FIXED = "D22-M150"  # Düse und Leermasse auf den Stufen von R0

ROCKET_COLUMNS = [
    "label", "v_bottle", "d_body", "p0_gauge", "d_nozzle", "m_empty", "status",
    "punkte_gueltig", "apogaeum_le0", "f_max_pct", "innen", "h_max_m",
    "t_client_s", "t_lauf_s", "aufrufe",
]


def yes_no(flag):
    return "ja" if flag else "nein"


def fill_pct(i):
    """Füllstand von Schritt i in Prozent (ganzzahlig, aus dem Index)."""
    return 5 + i


def is_finite_cell(cell):
    try:
        return math.isfinite(float(cell))
    except ValueError:
        return False


def load_runs(path):
    """Liest laeufe.csv und prüft Reihenfolge, Status, Dateinamen und Zeiten."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != run.RUNS_COLUMNS:
            raise ValueError("laeufe.csv: Spalten weichen von run.py ab")
        raw = list(reader)
    plan = [label for label, _ in run.rockets()]
    if not raw or [r["label"] for r in raw] != plan[:len(raw)]:
        raise ValueError("laeufe.csv: Reihenfolge weicht vom Plan ab")
    complete = len(raw) == len(plan)
    rows = {}
    for k, r in enumerate(raw):
        where = f"laeufe.csv {r['label']}"
        if r["status"] not in ALL_STATUSES:
            raise ValueError(f"{where}: unbekannter Status {r['status']}")
        stop, last = r["status"] in run.STOP_STATUSES, k == len(raw) - 1
        if stop and not last:
            raise ValueError(f"{where}: Abbruchstatus nicht in der letzten Zeile")
        if last and not complete and not stop:
            raise ValueError("laeufe.csv: Zeilen fehlen ohne Abbruchstatus")
        if int(r["n_steps"]) != run.N_STEPS:
            raise ValueError(f"{where}: n_steps weicht ab")
        want = f"{r['label']}_serie_{r['series_id']}.csv" if r["status"] == "201" else ""
        if r["file"] != want:
            raise ValueError(f"{where}: Dateiname weicht ab")
        t_client, t_lauf = float(r["t_client_s"]), float(r["t_lauf_s"])
        if not (t_client > 0 and t_lauf >= t_client):
            raise ValueError(f"{where}: Zeiten unplausibel")
        rows[r["label"]] = {
            "status": r["status"], "series_id": r["series_id"], "file": r["file"],
            "t_client": t_client, "t_lauf": t_lauf, "aufrufe": int(r["aufrufe"]),
        }
    return rows


def load_points(path, series_id, config):
    """Punkte eines Exports: (gültig, Apogäum oder None) je Schritt, Struktur geprüft."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    run.check_csv(rows, int(series_id), config, run.N_STEPS)
    points = []
    for row in rows:
        valid = all(is_finite_cell(row[col]) for col in RESULT_COLUMNS)
        points.append((valid, float(row["apogee"]) if valid else None))
    return points


def evaluate_rocket(label, config, run_row, points):
    """Kennzahlen einer Rakete; points ist None ohne Export (422, 504, nicht gemessen)."""
    result = {
        "label": label, "config": config,
        "status": run_row["status"] if run_row else "nicht gemessen",
        "valid": 0, "le0": 0, "f_max": None, "innen": None, "h_max": None,
        "curve": [None] * run.N_STEPS,
        "t_client": run_row["t_client"] if run_row else None,
        "t_lauf": run_row["t_lauf"] if run_row else None,
        "aufrufe": run_row["aufrufe"] if run_row else None,
    }
    if points is None:
        return result
    best = None
    for i, (valid, apogee) in enumerate(points):
        if not valid:
            continue
        result["valid"] += 1
        result["curve"][i] = apogee
        if apogee <= 0:
            result["le0"] += 1
        if best is None or apogee > best[1]:  # strikt: bei Gleichstand bleibt der kleinere
            best = (i, apogee)
    if best is not None:
        result["f_max"] = fill_pct(best[0])
        result["innen"] = result["f_max"] not in (fill_pct(0), fill_pct(run.N_STEPS - 1))
        result["h_max"] = best[1]
    return result


def evaluate(runs, points_by_label):
    return [evaluate_rocket(label, config, runs.get(label), points_by_label.get(label))
            for label, config in run.rockets()]


def summary(rockets):
    measured = [r for r in rockets if r["t_lauf"] is not None]
    with_max = [r for r in rockets if r["f_max"] is not None]
    t_lauf = sum(r["t_lauf"] for r in measured)
    flights = sum(run.N_STEPS for r in rockets if r["status"] == "201")
    valid = sum(r["valid"] for r in rockets)
    return {
        "valid": valid, "points": N_POINTS, "kpi": valid == N_POINTS,
        "status": {s: sum(1 for r in rockets if r["status"] == s)
                   for s in ALL_STATUSES + ("nicht gemessen",)},
        "le0": sum(r["le0"] for r in rockets),
        "le0_rockets": sum(1 for r in rockets if r["le0"] > 0),
        "innen": sum(1 for r in with_max if r["innen"]), "with_max": len(with_max),
        "f_range": ((min(r["f_max"] for r in with_max), max(r["f_max"] for r in with_max))
                    if with_max else None),
        "t_lauf": t_lauf, "t_client": sum(r["t_client"] for r in measured),
        "aufrufe": sum(r["aufrufe"] for r in measured), "flights": flights,
        "rate": flights / t_lauf if t_lauf > 0 else None,
    }


def rep(x):
    return "" if x is None else repr(x)


def write_rockets_csv(rockets, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(ROCKET_COLUMNS)
        for r in rockets:
            c = r["config"]
            writer.writerow([
                r["label"], repr(c["v_bottle"]), repr(c["d_body"]), repr(c["p0_gauge"]),
                repr(c["d_nozzle"]), repr(c["m_empty"]), r["status"], r["valid"], r["le0"],
                rep(r["f_max"]), "" if r["innen"] is None else yes_no(r["innen"]),
                rep(r["h_max"]), rep(r["t_client"]), rep(r["t_lauf"]), rep(r["aufrufe"]),
            ])


def de(x, digits):
    """Zahl mit fester Nachkommazahl und Dezimalkomma; None -> n. a."""
    if x is None:
        return "n. a."
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


def write_md(rockets, s, path):
    share = 100 * s["valid"] / s["points"]
    st = s["status"]
    lines = [
        "# Parameterstudie (54 Raketen, Füllstand 5 bis 95 %, 91 Schritte)",
        "",
        f"KPI Konfigurationsbandbreite: A = {s['valid']} von {s['points']} Punkten gültig "
        f"({de(share, 2)} %); Schwelle 100 %: {'erfüllt' if s['kpi'] else 'NICHT erfüllt'}.",
        f"Serien: 201 = {st['201']}; 422 = {st['422']}; 504 = {st['504']}; "
        f"Timeout = {st['timeout']}; nicht gemessen = {st['nicht gemessen']}.",
        f"Apogäum <= 0 (gültig, getrennt gezählt): {s['le0']} Punkte bei "
        f"{s['le0_rockets']} Raketen.",
        "",
        "Beschreibend (kein KPI):",
        f"- f_max innen (weder 5 % noch 95 %): {s['innen']} von {s['with_max']} Raketen.",
        "- f_max Spannweite: " + ("n. a." if s["f_range"] is None else
                                  f"{s['f_range'][0]} bis {s['f_range'][1]} %") + ".",
        f"- Zeit gesamt (Summe t_lauf_s): {de(s['t_lauf'], 1)} s; Summe t_client_s: "
        f"{de(s['t_client'], 1)} s; Aufrufe gesamt: {s['aufrufe']}.",
        f"- Flüge je Sekunde (Flüge / Summe t_lauf_s): {de(s['rate'], 2)} "
        f"({s['flights']} Flüge).",
        "",
        "## Je Rakete",
        "",
        "| Rakete | Status | gültig | Apogäum <= 0 | f_max in % | innen | h_max in m |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rockets:
        lines.append(
            f"| {r['label']} | {r['status']} | {r['valid']} | {r['le0']} | "
            f"{'n. a.' if r['f_max'] is None else r['f_max']} | "
            f"{'n. a.' if r['innen'] is None else yes_no(r['innen'])} | {de(r['h_max'], 2)} |"
        )
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def figure_rockets(rockets):
    """Raketen der Abbildung: je Flasche ein Feld, je Druck eine Linie (Düse/Masse fest)."""
    by_label = {r["label"]: r for r in rockets}
    panels = []
    for b_label, _ in run.BOTTLES:
        lines = [(p_label, by_label[f"{b_label}-{p_label}-{FIGURE_FIXED}"])
                 for p_label, _ in run.PRESSURES]
        panels.append((b_label, lines))
    return panels


def plot(rockets, out_dir):
    """Apogäum über Füllstand; ein Feld je Flasche, eine Linie je Startdruck."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    matplotlib.rcParams.update({"svg.hashsalt": "parameterstudie", "font.size": 9})
    comma = FuncFormatter(lambda v, _pos: f"{v:g}".replace(".", ",").replace("-", "−"))
    styles = {"P3": dict(color="0.55", linestyle=":"), "P5": dict(color="black", linestyle="-"),
              "P7": dict(color="0.3", linestyle="--")}
    titles = {b: f"{de(v['v_bottle'] * 1e3, 1)} l, {de(v['d_body'] * 1e3, 0)} mm"
              for b, v in run.BOTTLES}
    names = {p: f"{de(v['p0_gauge'] / 1e5, 0)} bar" for p, v in run.PRESSURES}
    xs = [fill_pct(i) for i in range(run.N_STEPS)]

    fig, axes = plt.subplots(1, len(run.BOTTLES), figsize=(6.3, 2.8), sharey=True)
    for ax, (b_label, lines) in zip(axes, figure_rockets(rockets)):
        for p_label, r in lines:
            ys = [math.nan if y is None else y for y in r["curve"]]
            ax.plot(xs, ys, linewidth=1.0, label=names[p_label], **styles[p_label])
            if r["f_max"] is not None:
                ax.plot([r["f_max"]], [r["h_max"]], marker="o", markersize=3.5,
                        color=styles[p_label]["color"], linestyle="none")
        ax.set_title(titles[b_label], fontsize=9)
        ax.set_xlim(0, 100)
        ax.set_xlabel("Füllstand in %")
        ax.xaxis.set_major_formatter(comma)
        ax.yaxis.set_major_formatter(comma)
        ax.grid(True, linewidth=0.3, color="0.8")
    axes[0].set_ylabel("Apogäum in m")
    axes[-1].legend(title="Startdruck", fontsize=7, title_fontsize=7, frameon=False,
                    loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.tight_layout()
    fig.savefig(out_dir / "abbildung_fuellstand.png", dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / "abbildung_fuellstand.svg", metadata={"Date": None})
    plt.close(fig)


OUTPUTS = ["parameterstudie.csv", "parameterstudie.md",
           "abbildung_fuellstand.png", "abbildung_fuellstand.svg"]


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR):
    runs = load_runs(data_dir / run.RUNS_NAME)
    configs = dict(run.rockets())
    points = {label: load_points(data_dir / r["file"], r["series_id"], configs[label])
              for label, r in runs.items() if r["status"] == "201"}
    rockets = evaluate(runs, points)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_rockets_csv(rockets, out_dir / "parameterstudie.csv")
    write_md(rockets, summary(rockets), out_dir / "parameterstudie.md")
    plot(rockets, out_dir)
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())