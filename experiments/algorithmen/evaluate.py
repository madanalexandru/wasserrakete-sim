"""Auswertung Algorithmenvergleich: K1, K2, Vorhersagen H1 bis H3, Zeiten invers.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitte 2 und 3,
Nachtrag 3 und 4)

Liest data/zeiten.csv, die Exporte aus data/, die Raketen im Vergleich aus
../durchsatz/results/monotonie.csv und die Schwellen S aus
../cw_sensitivitaet/results/kennzahlen.csv. Schreibt nach results/:
    suchen.csv                 je Suche, volle Genauigkeit
    algorithmen.csv            je Rakete und Verfahren, volle Genauigkeit
    algorithmen.md             gerundet, Dezimalkomma, für den Bericht
    abbildung_suchaufwand.png  300 dpi
    abbildung_suchaufwand.svg  Vektorgrafik
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python algorithmen/evaluate.py"
"""

import csv
import statistics
import sys
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
CW_DIR = HERE.parent / "cw_sensitivitaet"

# Vorhersagen aus der Vorab-Notiz, Abschnitt 3 (Überdruck in Pa)
H1_BINARY = 22
H2_BANDS = [
    (1e3, 51e3, 18),
    (51e3, 101e3, 19),
    (101e3, 201e3, 21),
    (201e3, 401e3, 23),
    (401e3, 1e6, 25),
]
# Nachtrag 4: Prüfstellen der Exponentialsuche sowie P_MIN und P_MAX
GRENZEN = [1e3, 51e3, 101e3, 201e3, 401e3, 801e3, 1e6]
MIN_ABSTAND = 1.0  # Pa

# Schwellen aus Abschnitt 2
T_MAX_S = 300.0
CALLS_MAX = 3

SEARCH_COLUMNS = [
    "label", "searcher", "series_id", "nr", "target_m", "p_star_pa", "apogee_m",
    "search_evaluations", "delta_pct", "k2_erfuellt", "grenzfall", "vorhersage",
    "vorhersage_erfuellt",
]
GROUP_COLUMNS = [
    "label", "searcher", "status", "suchen", "eval_median", "eval_min", "eval_max",
    "eval_summe", "delta_max_pct", "S_pct", "k2_erfuellt", "grenzfaelle",
    "vorhersage_treffer", "vorhersage_gewertet", "t_client_s", "aufrufe", "zeit_erfuellt",
]


def yes_no(flag):
    return "ja" if flag else "nein"


def h2_expected(p):
    """Vorhergesagte Auswertungen der Exponentialsuche; None im Grenzfall."""
    if is_boundary(p):
        return None
    for lo, hi, n in H2_BANDS:
        if lo < p < hi:
            return n
    raise ValueError("p* außerhalb des Suchbereichs")


def is_boundary(p):
    return any(abs(p - g) < MIN_ABSTAND for g in GRENZEN)


def load_kennzahlen(cw_dir):
    with open(cw_dir / "results" / "kennzahlen.csv", newline="", encoding="utf-8") as f:
        return {r["label"]: float(r["S_pct"]) for r in csv.DictReader(f)}


def load_times(path, labels):
    """Liest zeiten.csv und prüft Reihenfolge und Status (201 oder 422)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != run.TIMES_COLUMNS:
            raise ValueError("zeiten.csv: Spalten weichen von run.py ab")
        raw = list(reader)
    expected = [(label, s) for label in labels for s in run.SEARCHERS]
    if [(r["label"], r["searcher"]) for r in raw] != expected:
        raise ValueError("zeiten.csv: Zeilen fehlen oder Reihenfolge weicht ab")
    rows = []
    for r in raw:
        where = f"zeiten.csv {r['label']} {r['searcher']}"
        if r["status"] not in ("201", "422"):
            raise ValueError(f"{where}: Status {r['status']} (Auswertung setzt 201/422 voraus)")
        if int(r["n_steps"]) != run.N_TARGETS:
            raise ValueError(f"{where}: n_steps weicht ab")
        want = (f"{r['label']}_{r['searcher']}_serie_{r['series_id']}.csv"
                if r["status"] == "201" else "")
        if r["file"] != want:
            raise ValueError(f"{where}: Dateiname weicht ab")
        t_client = float(r["t_client_s"])
        if not t_client > 0:
            raise ValueError(f"{where}: Zeit nicht positiv")
        rows.append({
            "label": r["label"], "searcher": r["searcher"], "status": r["status"],
            "series_id": r["series_id"], "file": r["file"], "t_client": t_client,
            "aufrufe": int(r["aufrufe"]),
        })
    return rows


def load_searches(path, series_id, searcher):
    """Suchen eines Exports (Struktur geprüft)."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != run.N_TARGETS:
        raise ValueError(f"{path.name}: Zeilenzahl weicht ab")
    if any(r["series_id"] != series_id or r["searcher"] != searcher for r in rows):
        raise ValueError(f"{path.name}: fremde Serie oder anderes Verfahren")
    return [{
        "target": float(r["target_apogee"]), "p_star": float(r["p0_gauge"]),
        "apogee": float(r["apogee"]), "evals": int(r["search_evaluations"]),
    } for r in rows]


def assess(search, searcher, S_pct):
    """Kennzahlen einer Suche: delta, K2, Grenzfall, Vorhersage."""
    delta = 100 * abs(search["apogee"] - search["target"]) / search["target"]
    out = {
        **search, "delta_pct": delta, "k2": delta <= S_pct / 100,
        "grenzfall": is_boundary(search["p_star"]), "vorhersage": None, "treffer": None,
    }
    if searcher == "binary":
        out["vorhersage"] = H1_BINARY
    elif searcher == "exponential":
        out["vorhersage"] = h2_expected(search["p_star"])
    if out["vorhersage"] is not None:
        out["treffer"] = search["evals"] == out["vorhersage"]
    return out


def evaluate(times, searches_by_file, S):
    """Je Serie eine Gruppe mit allen Suchen und Kennzahlen."""
    groups = []
    for t in times:
        found = searches_by_file.get(t["file"], [])
        items = [assess(s, t["searcher"], S[t["label"]]) for s in found]
        evals = [s["evals"] for s in items]
        rated = [s for s in items if s["treffer"] is not None]
        groups.append({
            **t, "S_pct": S[t["label"]], "items": items,
            "eval": (statistics.median(evals), min(evals), max(evals), sum(evals))
            if evals else None,
            "delta_max": max((s["delta_pct"] for s in items), default=None),
            "k2": all(s["k2"] for s in items) if items else None,
            "grenzfaelle": sum(1 for s in items if s["grenzfall"]),
            "treffer": sum(1 for s in rated if s["treffer"]),
            "gewertet": len(rated),
            "zeit": t["t_client"] < T_MAX_S,
        })
    return groups


def summary(groups):
    by = {s: [g for g in groups if g["searcher"] == s] for s in run.SEARCHERS}
    items = [s for g in groups for s in g["items"]]
    interp = [g for g in by["interpolation"] if g["eval"] is not None]
    return {
        "serien": len(groups),
        "k1": sum(1 for g in groups if g["status"] == "201"),
        "suchen": len(items),
        "k2": sum(1 for s in items if s["k2"]),
        "h1": (sum(g["treffer"] for g in by["binary"]), sum(g["gewertet"] for g in by["binary"])),
        "h2": (sum(g["treffer"] for g in by["exponential"]),
               sum(g["gewertet"] for g in by["exponential"])),
        "h2_grenzfaelle": sum(g["grenzfaelle"] for g in by["exponential"]),
        "h3": (sum(1 for g in interp if g["eval"][0] < H1_BINARY), len(interp)),
        "zeit": sum(1 for g in groups if g["zeit"]),
        "aufwand": sum(1 for g in groups if g["aufrufe"] <= CALLS_MAX),
        "summe": {s: sum(g["eval"][3] for g in by[s] if g["eval"]) for s in run.SEARCHERS},
        "t_client": {s: [g["t_client"] for g in by[s]] for s in run.SEARCHERS},
    }


def rep(x):
    return "" if x is None else repr(x)


def write_searches_csv(groups, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(SEARCH_COLUMNS)
        for g in groups:
            for i, s in enumerate(g["items"]):
                writer.writerow([
                    g["label"], g["searcher"], g["series_id"], i, repr(s["target"]),
                    repr(s["p_star"]), repr(s["apogee"]), s["evals"], repr(s["delta_pct"]),
                    yes_no(s["k2"]), yes_no(s["grenzfall"]), rep(s["vorhersage"]),
                    "" if s["treffer"] is None else yes_no(s["treffer"]),
                ])


def write_groups_csv(groups, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(GROUP_COLUMNS)
        for g in groups:
            e = g["eval"] or ("", "", "", "")
            writer.writerow([
                g["label"], g["searcher"], g["status"], len(g["items"]),
                *[rep(v) if v != "" else "" for v in e],
                rep(g["delta_max"]), repr(g["S_pct"]),
                "" if g["k2"] is None else yes_no(g["k2"]), g["grenzfaelle"],
                g["treffer"], g["gewertet"], repr(g["t_client"]), g["aufrufe"],
                yes_no(g["zeit"]),
            ])


def de(x, digits):
    """Zahl mit fester Nachkommazahl und Dezimalkomma; None -> n. a."""
    if x is None:
        return "n. a."
    return f"{x:.{digits}f}".replace(".", ",")


def de_g(x):
    """Zahl in Kurzform (z. B. Median 21,5) mit Dezimalkomma."""
    return f"{x:g}".replace(".", ",")


def write_md(groups, s, path):
    lines = [
        "# Algorithmenvergleich (inverser Modus, 40 Zielhöhen je Serie)",
        "",
        f"K1 (konvergiert): {s['k1']} von {s['serien']} Serien.",
        f"K2 (delta <= S/100): {s['k2']} von {s['suchen']} Suchen.",
        f"H1 (binär = {H1_BINARY}): {s['h1'][0]} von {s['h1'][1]} Suchen.",
        f"H2 (exponentiell nach Tabelle): {s['h2'][0]} von {s['h2'][1]} gewerteten "
        f"Suchen; {s['h2_grenzfaelle']} Grenzfälle getrennt.",
        f"H3 (Interpolation, Median < {H1_BINARY}): {s['h3'][0]} von {s['h3'][1]} Raketen.",
        f"Zeit invers: {s['zeit']} von {s['serien']} Serien mit t_Client < "
        f"{de(T_MAX_S, 0)} s.",
        f"Aufwand invers: {s['aufwand']} von {s['serien']} Serien mit höchstens "
        f"{CALLS_MAX} Aufrufen.",
        "",
        "## Auswertungen je Suche: Median (Min. bis Max.)",
        "",
        "| Rakete | binär | exponentiell | Interpolation | delta max. in % | S/100 in % |",
        "|---|---|---|---|---|---|",
    ]
    for label in dict.fromkeys(g["label"] for g in groups):
        mine = {g["searcher"]: g for g in groups if g["label"] == label}
        cells = []
        for searcher in run.SEARCHERS:
            e = mine[searcher]["eval"]
            cells.append("n. a." if e is None else f"{de_g(e[0])} ({e[1]} bis {e[2]})")
        deltas = [g["delta_max"] for g in mine.values() if g["delta_max"] is not None]
        lines.append(
            f"| {label} | {' | '.join(cells)} | "
            f"{de(max(deltas) if deltas else None, 5)} | "
            f"{de(mine['binary']['S_pct'] / 100, 5)} |"
        )
    lines += [
        "",
        "## Summe der Auswertungen und Zeiten je Verfahren",
        "",
        "| Verfahren | Auswertungen gesamt | t_Client in s: Median (Min. bis Max.) |",
        "|---|---|---|",
    ]
    for searcher in run.SEARCHERS:
        t = s["t_client"][searcher]
        lines.append(
            f"| {searcher} | {s['summe'][searcher]} | {de(statistics.median(t), 1)} "
            f"({de(min(t), 1)} bis {de(max(t), 1)}) |"
        )
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(groups, out_dir):
    """Auswertungen über p* je Verfahren, mit H2-Stufen und der Linie H1."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    matplotlib.rcParams.update({"svg.hashsalt": "algorithmen", "font.size": 9})
    comma = FuncFormatter(lambda v, _pos: f"{v:g}".replace(".", ",").replace("-", "−"))
    styles = {
        "binary": dict(marker="o", facecolors="none", edgecolors="black", label="binär"),
        "exponential": dict(marker="s", facecolors="0.6", edgecolors="0.6",
                            label="exponentiell"),
        "interpolation": dict(marker="^", facecolors="black", edgecolors="black",
                              label="Interpolation (Illinois)"),
    }

    fig, ax = plt.subplots(figsize=(6.3, 3.4))  # ca. 16 cm x 8,6 cm
    for searcher in run.SEARCHERS:
        xs = [s["p_star"] / 1e3 for g in groups if g["searcher"] == searcher for s in g["items"]]
        ys = [s["evals"] for g in groups if g["searcher"] == searcher for s in g["items"]]
        ax.scatter(xs, ys, s=10, linewidths=0.6, **styles[searcher])
    step_x, step_y = [], []
    for lo, hi, n in H2_BANDS:
        step_x += [lo / 1e3, hi / 1e3]
        step_y += [n, n]
    ax.plot(step_x, step_y, color="0.4", linestyle="--", linewidth=0.8,
            label="Vorhersage H2")
    ax.axhline(H1_BINARY, color="black", linestyle=":", linewidth=0.8,
               label=f"Vorhersage H1 ({H1_BINARY})")
    ax.set_xlabel(r"gefundener Startdruck $p^*$ in kPa (Überdruck)")
    ax.set_ylabel("Auswertungen (Flüge) je Suche")
    ax.set_xlim(0, 1000)
    ax.xaxis.set_major_formatter(comma)
    ax.yaxis.set_major_formatter(comma)
    ax.grid(True, linewidth=0.3, color="0.8")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(out_dir / "abbildung_suchaufwand.png", dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / "abbildung_suchaufwand.svg", metadata={"Date": None})
    plt.close(fig)


OUTPUTS = ["suchen.csv", "algorithmen.csv", "algorithmen.md",
           "abbildung_suchaufwand.png", "abbildung_suchaufwand.svg"]


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR, durchsatz_dir=run.DURCHSATZ_DIR,
         cw_dir=CW_DIR):
    mono = run.load_monotonie(durchsatz_dir / "results" / "monotonie.csv")
    labels = [label for label, (included, _) in mono.items() if included]
    times = load_times(data_dir / run.TIMES_NAME, labels)
    searches = {t["file"]: load_searches(data_dir / t["file"], t["series_id"], t["searcher"])
                for t in times if t["status"] == "201"}
    groups = evaluate(times, searches, load_kennzahlen(cw_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_searches_csv(groups, out_dir / "suchen.csv")
    write_groups_csv(groups, out_dir / "algorithmen.csv")
    write_md(groups, summary(groups), out_dir / "algorithmen.md")
    plot(groups, out_dir)
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())