# Vorab-Notiz: Parameterstudie und KPI Konfigurationsbandbreite

Erstellt: 11.11.2026, VOR jeder Messung der Parameterstudie.
Zweck: Bericht 2.2 und 3; Teilfrage 2.
Modellversion: "1". Repo-Stand bei Erstellung: 28c9139.

## 0. Vorab bekannt

- Druckachse 1 bis 1000 kPa für R0 bis R9 gemessen
  (experiments/durchsatz); Monotonie M2 bei allen 10 Raketen.
- Tool-Vergleich: R0 bis R9 einzeln innerhalb S (10 von 10). Für
  1,5 l / 5 bar / 22 mm / 150 g sind damit Apogäen bei 0,3, 0,5 und
  0,7 l Wasser bekannt (R3, R0, R4). Die Form der Füllstandkurve ist
  an drei Stellen vorab bekannt.
- Durchsatz vorwärts (KPI 96): Median 7,3 bis 19,5 Flüge/s je Rakete.
- Extremwerte außerhalb dieser Studie ergeben 422 (z. B. Düse 0,1 mm
  nach ca. 60 s).
- Code: Scheitert ein Schritt einer Vorwärtsserie, antwortet die API
  für die ganze Serie mit 422 und speichert keinen Flug.
- Keine Werte aus Füllstand-Serien.

## 1. Versuchsplan

Raster aus den Stufen des Validierungssatzes R0 bis R9. Je
Rasterpunkt eine Rakete mit einer Vorwärtsserie über den Füllstand.

| Faktor | Stufen | Herkunft |
|---|---|---|
| Flasche (v_bottle, d_body) | 1,0 l / 79 mm; 1,5 l / 90 mm; 2,0 l / 102 mm | R8, R0, R9 |
| Startdruck p0_gauge | 3; 5; 7 bar | R1, R0, R2 |
| Düse d_nozzle | 15; 22 mm | R5, R0 |
| Leermasse m_empty | 100; 150; 250 g | R6, R0, R7 |

- 3 × 3 × 2 × 3 = 54 Raketen.
- Alle Werte plausibel, NICHT gemessen. Durchmesser 79 und 102 mm
  sind Anhaltswerte, nicht zitierfähig.
- Fest: c_w = 0,345 (c_ref, wie KPI 96), temp0 Standard, ohne
  Geometrie (Flugphysik nutzt sie nicht).
- Serie: param_name v_water0 von 0,05·V bis 0,95·V, 91 Schritte.
  Schritt i (0 bis 90) hat den Füllstand f_i = (5 + i) / 100.
- Begründung Füllstand: ganzer physikalischer Bereich. Die Ränder 5
  und 95 % sind eine Setzung ohne Quelle (das Schema verlangt
  0 < v_water0 < v_bottle).
- v_water0 der angelegten Rakete = 0,05·V (die Serie überschreibt es).
- Summe: 54 × 91 = 4914 Flüge; 54 × 3 = 162 Aufrufe (Rakete, Serie,
  CSV).
- Validierung: Rasterpunkte gelten als nicht gegen das Referenztool
  geprüft, auch wo sie rechnerisch einer Rakete aus R0 bis R9
  entsprechen.

## 2. KPI Konfigurationsbandbreite

- Definition: Abdeckung A = gültige Punkte / 4914.
- Gültig: Serie mit Status 201, CSV mit 91 Zeilen, alle
  Ergebnisspalten endlich.
- Schwelle: A = 100 %.
- Begründung: anforderungsbezogen. Das Tool soll den vorab
  festgelegten Bereich lückenlos rechnen. c_w wirkt auf die Höhe,
  nicht auf die Rechenbarkeit; ein Bezug zur c_w-Sensitivität
  entfällt (wie KPI 96).
- Verfehlt: unverändert berichten; Fehlertexte untersuchen;
  begründete Änderung als datierter Nachtrag; erneut messen; beide
  Ergebnisse berichten.

## 3. Zählregeln

- Apogäum <= 0 (hebt nicht ab): gültig; Anzahl getrennt berichtet.
- 422 einer Serie: alle 91 Punkte nicht gültig; Fehlertext
  gespeichert; Messung geht weiter.
- 504 oder Client-Timeout (330 s): Zeile speichern, Messung beenden.
- Andere Fehler: Abbruch ohne Schreiben.

## 4. Beschreibend (kein KPI, keine Hypothese)

- Je Rakete: Füllstand des größten Apogäums f_max (Rasterwert; bei
  Gleichstand der kleinste). "Innen", wenn f_max weder 5 % noch 95 %.
- Je Rakete: größtes Apogäum; Anzahl Apogäen <= 0.
- Gesamte Wanduhrzeit der Studie und Anzahl Aufrufe
  (Experimentierbarkeit, Teilfrage 2).
- Einordnung mit Einzelwerten aus Quellen nur in der Discussion,
  nach Seitenprüfung: [QUELLE PRÜFEN].

## 5. Ablauf und Ausgaben

- Ordner experiments/parameterstudie/; Hilfsfunktionen kopiert;
  Basiswerte aus durchsatz/run.py kopiert und per Test auf
  Gleichheit geprüft.
- Aufwärmlauf: Stufen von R0, 10 Schritte, nicht gewertet.
- Reihenfolge: ein Durchgang, geschachtelt Flasche, Druck, Düse,
  Leermasse (Stufen wie in der Tabelle von oben nach unten).
- Rohdaten (data/, CRLF): 54 CSV-Exporte unverändert und laeufe.csv
  (eine Zeile je Serie: Rakete, Status, Fehlertext, t_Client,
  Aufrufe).
- Auswertung (results/, LF): parameterstudie.csv, parameterstudie.md
  und eine Abbildung. Die Abbildung zeigt das Apogäum über dem
  Füllstand, ein Feld je Flasche und eine Linie je Druck. Düse und
  Leermasse stehen auf den Stufen von R0 (22 mm, 150 g). Ausgabe als
  PNG 300 dpi und SVG mit Dezimalkomma.
- Messumgebung wie Nachtrag 1 in kpi_uebrige_plan.md; während der
  Messung keine anderen rechenintensiven Programme.

## 6. Regeln

- Skripte geben nur Ja/Nein und Dateinamen aus, keine Messwerte.
- Rohdaten unverändert ins Repo, dann Auswertung mit Tests
  committen, erst danach Werte ansehen.
- Änderungen an dieser Notiz nur als datierter Nachtrag.