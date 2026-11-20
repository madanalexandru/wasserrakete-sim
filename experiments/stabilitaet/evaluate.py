"""Auswertung R0G: Stabilitätswerte (beschreibend) und Kontrolle des Apogäums.

Plan: docs/validation/stabilitaet_plan.md (Abschnitt 4)

Liest data/manifest.csv und die JSON-Antworten. Schreibt nach results/:
    stabilitaet.csv  volle Genauigkeit, Punkt als Dezimaltrenner
    stabilitaet.md   gerundet, Dezimalkomma, für den Bericht
Auf der Konsole erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python stabilitaet/evaluate.py
"""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
OUTPUTS = ["stabilitaet.csv", "stabilitaet.md"]
FIELDS = [
    ("x_cp", "Druckpunkt x_CP ab Nasenspitze", "m"),
    ("x_cg_start", "Schwerpunkt mit Startwasser", "m"),
    ("x_cg_empty", "Schwerpunkt leer", "m"),
    ("margin_start", "Stabilitätsmaß beim Start", "Kaliber"),
    ("margin_empty", "Stabilitätsmaß leer", "Kaliber"),
]


def load(data_dir):
    """Dict Kürzel -> {'rocket': ..., 'flight': ...} aus manifest.csv."""
    with open(data_dir / "manifest.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if [r["label"] for r in rows] != ["R0", "R0G"]:
        raise ValueError("manifest.csv muss genau R0 und R0G enthalten")
    out = {}
    for r in rows:
        rocket = json.loads((data_dir / r["rocket_file"]).read_text(encoding="utf-8"))
        flight = json.loads((data_dir / r["flight_file"]).read_text(encoding="utf-8"))
        if rocket["id"] != int(r["rocket_id"]) or flight["id"] != int(r["flight_id"]):
            raise ValueError(f"{r['label']}: IDs passen nicht zu manifest.csv")
        out[r["label"]] = {"rocket": rocket, "flight": flight}
    return out


def evaluate(data):
    stab = data["R0G"]["rocket"]["stability"]
    if stab is None:
        raise ValueError("R0G hat keine Stabilitätswerte")
    h0, hg = data["R0"]["flight"]["apogee"], data["R0G"]["flight"]["apogee"]
    return {
        "values": {key: stab[key] for key, _, _ in FIELDS},
        "apogee_R0": h0,
        "apogee_R0G": hg,
        "apogee_gleich": h0 == hg,
    }


def de(x, digits):
    return f"{x:.{digits}f}".replace(".", ",").replace("-", "−")


def write_csv(res, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["groesse", "wert", "einheit"])
        for key, _, unit in FIELDS:
            w.writerow([key, repr(res["values"][key]), unit])
        w.writerow(["apogee_R0", repr(res["apogee_R0"]), "m"])
        w.writerow(["apogee_R0G", repr(res["apogee_R0G"]), "m"])
        w.writerow(["apogee_gleich", "ja" if res["apogee_gleich"] else "nein", ""])


def write_md(res, path):
    lines = [
        "# R0G: Stabilitätswerte (beschreibend) und Kontrolle",
        "",
        "Geometrie: Annahme laut docs/validation/stabilitaet_plan.md. Keine Bewertung,",
        "da für eine Warnschwelle keine Quelle vorliegt.",
        "",
        "| Größe | Wert | Einheit |",
        "|---|---|---|",
    ]
    for key, label, unit in FIELDS:
        lines.append(f"| {label} | {de(res['values'][key], 3)} | {unit} |")
    gleich = "ja (bitgleich)" if res["apogee_gleich"] else "NEIN"
    lines += [
        "",
        "| Kontrolle | Wert |",
        "|---|---|",
        f"| Apogäum R0 | {de(res['apogee_R0'], 2)} m |",
        f"| Apogäum R0G | {de(res['apogee_R0G'], 2)} m |",
        f"| Apogäum gleich | {gleich} |",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(data_dir=DATA_DIR, out_dir=RESULTS_DIR):
    res = evaluate(load(data_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(res, out_dir / OUTPUTS[0])
    write_md(res, out_dir / OUTPUTS[1])
    for name in OUTPUTS:
        print(f"geschrieben: {out_dir.name}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())