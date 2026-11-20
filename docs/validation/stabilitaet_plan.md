# Vorab-Notiz: Beispielrakete mit Nasenkegel und Finnen (R0G)

Festgelegt: 20.11.2026, vor jeder Rechnung mit dieser Geometrie.

## 1 Zweck

Die Aufgabenstellung nennt Maße und Lage von Finnen und Nasenkegel als
Teil der Konfiguration. Das Tool kann sie (Stabilität nach Barrowman),
aber keine Rakete der bisherigen Experimente nutzt sie. Dieses Experiment
zeigt an einem Beispiel, dass die Konfiguration mit Nasenkegel und Finnen
über die API von Anfang bis Ende funktioniert (Teilfrage 2,
Konfigurationsbandbreite).

Es belegt NICHT, dass die Stabilitätswerte realistisch sind: Die
Geometrie ist eine Annahme, nicht gemessen und nicht aus einer Quelle.

## 2 Raketen

- R0: wie die Basisrakete in cw_sensitivitaet/run.py (1,5 l, 90 mm,
  0,5 l Wasser, 5 bar Überdruck, Düse 22 mm, Leermasse 150 g),
  c_w = 0,345 (c_ref), ohne Geometrie.
- R0G: wie R0, dazu folgende Geometrie (alle Werte ANNAHME):

| Feld | Wert | Bedeutung |
|------|------|-----------|
| nose_shape | ogive | Nasenkegel als Ogive |
| l_nose | 0,10 m | Länge Nasenkegel |
| n_fins | 3 | Zahl der Finnen |
| fin_root_chord | 0,10 m | Finnentiefe am Rumpf |
| fin_tip_chord | 0,05 m | Finnentiefe außen |
| fin_span | 0,08 m | Spannweite |
| fin_sweep | 0,05 m | Pfeilung (Versatz der Vorderkante außen) |
| l_total | 0,42 m | Gesamtlänge (Flasche ca. 0,32 m + Nasenkegel) |
| x_fin | 0,32 m | Nasenspitze bis Finne (Finnen bündig am Heck) |
| x_cg_empty | 0,21 m | Schwerpunkt leer (Mitte der Gesamtlänge) |

## 3 Ablauf

1. run.py legt R0 und R0G über die API an (POST /api/rockets) und
   rechnet je einen Flug (POST /api/rockets/{id}/flights).
2. Die JSON-Antworten werden unverändert nach
   experiments/stabilitaet/data/ geschrieben.
3. evaluate.py schreibt results/stabilitaet.md.

## 4 Kennzahlen (beschreibend, ohne KPI, ohne Warnschwelle)

- Stabilitätswerte von R0G aus der API-Antwort: x_cp, x_cg_start,
  x_cg_empty, Stabilitätsmaß beim Start und leer (in Kalibern).
- Kontrolle: Das Apogäum von R0G ist bitgleich mit dem von R0, weil die
  Geometrie laut Methods nicht auf den Flug wirkt. Weicht es ab, wird
  das unverändert berichtet und die Ursache untersucht.

Für eine Warnschwelle liegt keine geprüfte Quelle vor (wie im Tool). Die
Werte werden deshalb nicht als stabil oder instabil bewertet.

## 5 Fehlerfall

Lehnt die API die Geometrie ab (HTTP 422), wird sie in einem datierten
Nachtrag geändert; der Grund wird genannt.

## 6 Vorwissen

Für diese Geometrie wurden vor dieser Notiz keine Stabilitätswerte
berechnet. Die Tests der Skripte nutzen eine andere Geometrie.