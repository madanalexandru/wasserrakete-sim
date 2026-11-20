"""Tests für evaluate.py mit erfundenen Testdaten (nicht die Messung).

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment python -W error -m unittest discover -s stabilitaet -v
"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import evaluate

STAB = {"x_cp": 0.5, "x_cg_start": 0.4, "x_cg_empty": 0.3, "margin_start": 1.25, "margin_empty": 2.5}


def make_data(tmp, apogee_g=50.0, labels=("R0", "R0G")):
    rows = []
    for i, label in enumerate(labels, start=1):
        rocket = {"id": i, "stability": STAB if label == "R0G" else None}
        flight = {"id": 10 + i, "rocket_id": i, "apogee": apogee_g if label == "R0G" else 50.0}
        (tmp / f"{label}_rakete.json").write_text(json.dumps(rocket), encoding="utf-8")
        (tmp / f"{label}_flug.json").write_text(json.dumps(flight), encoding="utf-8")
        rows.append({"label": label, "rocket_id": i, "flight_id": 10 + i,
                     "rocket_file": f"{label}_rakete.json", "flight_file": f"{label}_flug.json"})
    with open(tmp / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


class TestAuswertung(unittest.TestCase):
    def test_werte_und_kontrolle(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_data(Path(tmp))
            res = evaluate.evaluate(evaluate.load(Path(tmp)))
        self.assertEqual(res["values"], STAB)
        self.assertTrue(res["apogee_gleich"])

    def test_abweichendes_apogaeum_wird_berichtet(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_data(Path(tmp), apogee_g=50.0000001)
            res = evaluate.evaluate(evaluate.load(Path(tmp)))
        self.assertFalse(res["apogee_gleich"])

    def test_falsches_manifest_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_data(Path(tmp), labels=("R0G", "R0"))
            with self.assertRaises(ValueError):
                evaluate.load(Path(tmp))

    def test_ausgabedateien(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
            make_data(Path(tmp))
            with redirect_stdout(io.StringIO()) as s:
                self.assertEqual(evaluate.main(Path(tmp), Path(out)), 0)
            self.assertNotIn("1,25", s.getvalue())
            md = (Path(out) / "stabilitaet.md").read_text(encoding="utf-8")
            self.assertIn("| Stabilitätsmaß beim Start | 1,250 | Kaliber |", md)
            self.assertIn("| Apogäum gleich | ja (bitgleich) |", md)
            with open(Path(out) / "stabilitaet.csv", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], ["groesse", "wert", "einheit"])
            self.assertEqual(len(rows), 1 + 5 + 3)


if __name__ == "__main__":
    unittest.main()