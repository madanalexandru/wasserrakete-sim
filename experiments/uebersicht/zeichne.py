"""Übersichtsabbildung: System und Experiment-Workflow.

Zeigt nur Aufbau und Ablauf, keine Messwerte. Schreibt nach results/:
    abbildung_uebersicht.png  300 dpi
    abbildung_uebersicht.svg  Vektorgrafik

Alle Maße in Millimetern; die Zeichenfläche entspricht der Abbildung
(16 cm x 8 cm), eine Dateneinheit ist ein Millimeter.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python uebersicht/zeichne.py"
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"

WIDTH_MM, HEIGHT_MM = 160.0, 80.0
FONT_BOX = 7.0
FONT_TITLE = 7.5
FONT_NOTE = 6.5

# Rahmen (Bänder und Behälter): Schlüssel -> (Rechteck x0, y0, x1, y1, Titel, Eltern)
FRAMES = {
    "system": ((1, 43, 159, 79), "System (Docker Compose)", None),
    "backend": ((68, 45, 124, 75), "Backend (FastAPI)", "system"),
    "workflow": ((1, 1, 159, 39), "Experiment-Workflow", None),
}

# Kästen: Schlüssel -> (Rechteck, Text, Eltern)
BOXES = {
    "browser": ((4, 52, 26, 66), "Browser\n(HTML,\nVanilla JS)", "system"),
    "nginx": ((34, 52, 60, 66), "Nginx\nliefert Frontend,\nleitet /api/ weiter", "system"),
    "schema": ((70, 59, 96, 69), "Eingabeprüfung\n(Pydantic)", "backend"),
    "daten": ((98, 59, 122, 69), "Datenzugriff\n(SQLAlchemy)", "backend"),
    "physik": ((70, 47, 96, 57), "Physik: 3 Phasen,\nRK4, Ereignissuche", "backend"),
    "suche": ((98, 47, 122, 57), "Suchverfahren\n(Searchable)", "backend"),
    "postgres": ((132, 58, 156, 70), "PostgreSQL\n(rockets, series,\nflights)", "system"),
    "migrate": ((132, 46, 156, 54), "migrate\n(Alembic)", "system"),
    "notiz": ((4, 6, 25, 18), "Vorab-Notiz\n(KPI, Regeln)", "workflow"),
    "run": ((30, 6, 51, 18), "run.py\n(Messung)", "workflow"),
    "data": ((56, 6, 77, 18), "data/\n(Rohdaten,\nunverändert)", "workflow"),
    "evaluate": ((82, 6, 103, 18), "evaluate.py\n(mit Tests)", "workflow"),
    "results": ((108, 6, 129, 18), "results/\n(CSV, MD,\nPNG, SVG)", "workflow"),
    "bericht": ((134, 6, 155, 18), "Bericht\n(2.2, 3, 4)", "workflow"),
    "tool": ((56, 24, 77, 33), "Referenztool\n(Handeingabe)", "workflow"),
}

# Pfeile: (Punkte des Linienzugs, gestrichelt)
ARROWS = [
    ([(26, 63), (34, 63)], False),
    ([(60, 63), (70, 63)], False),
    ([(122, 64), (132, 64)], False),
    ([(144, 54), (144, 58)], False),
    ([(25, 12), (30, 12)], False),
    ([(51, 12), (56, 12)], False),
    ([(77, 12), (82, 12)], False),
    ([(103, 12), (108, 12)], False),
    ([(129, 12), (134, 12)], False),
    ([(66.5, 24), (66.5, 18)], False),
    ([(44, 18), (44, 52)], False),
    ([(49, 18), (49, 41), (83, 41), (83, 47)], True),
]

# Hinweise neben Pfeilen und Kästen: (x, y, Text, Ausrichtung, Eltern)
NOTES = [
    (14.5, 23.5, "vor der Messung\ncommittet", "center", "workflow"),
    (42, 30, "HTTP über Nginx", "right", "workflow"),
    (52, 36.5, "direkter Aufruf der Physik (nur Ereignissuche)", "left", "workflow"),
]


def draw():
    """Zeichnet die Abbildung; gibt (fig, Textobjekte mit Behälter) zurück."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, Rectangle
    from matplotlib.path import Path as MplPath

    matplotlib.rcParams.update({"svg.hashsalt": "uebersicht", "font.size": FONT_BOX})
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_MM / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH_MM)
    ax.set_ylim(0, HEIGHT_MM)
    ax.axis("off")

    texts = []
    for key, ((x0, y0, x1, y1), title, parent) in FRAMES.items():
        outer = parent is None
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=outer,
                               facecolor="0.95", edgecolor="0.3",
                               linewidth=0.8 if outer else 0.6,
                               linestyle="-" if outer else "--"))
        t = ax.text(x0 + 1.5, y1 - 1.2, title, ha="left", va="top",
                    fontsize=FONT_TITLE, fontweight="bold")
        texts.append(("titel", key, t))
    for key, ((x0, y0, x1, y1), label, _parent) in BOXES.items():
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="white",
                               edgecolor="black", linewidth=0.6))
        t = ax.text((x0 + x1) / 2, (y0 + y1) / 2, label, ha="center", va="center",
                    fontsize=FONT_BOX, linespacing=1.1)
        texts.append(("kasten", key, t))
    for points, dashed in ARROWS:
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1)
        ax.add_patch(FancyArrowPatch(path=MplPath(points, codes), arrowstyle="-|>",
                                     mutation_scale=6, linewidth=0.7, color="black",
                                     linestyle=(0, (3, 2)) if dashed else "-",
                                     shrinkA=0, shrinkB=0))
    for i, (x, y, label, align, _parent) in enumerate(NOTES):
        t = ax.text(x, y, label, ha=align, va="center", fontsize=FONT_NOTE,
                    fontstyle="italic", linespacing=1.1)
        texts.append(("hinweis", i, t))
    return fig, texts


def text_extents(fig, texts):
    """Ausdehnung jedes Texts in Millimetern: Liste (Art, Schlüssel, x0, y0, x1, y1)."""
    renderer = fig.canvas.get_renderer()
    scale = 25.4 / fig.dpi
    out = []
    for kind, key, t in texts:
        bb = t.get_window_extent(renderer=renderer)
        out.append((kind, key, bb.x0 * scale, bb.y0 * scale, bb.x1 * scale, bb.y1 * scale))
    return out


OUTPUTS = ["abbildung_uebersicht.png", "abbildung_uebersicht.svg"]


def main(out_dir=RESULTS_DIR):
    import matplotlib.pyplot as plt

    fig, _texts = draw()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / OUTPUTS[0], dpi=300, metadata={"Software": None})
    fig.savefig(out_dir / OUTPUTS[1], metadata={"Date": None})
    plt.close(fig)
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())