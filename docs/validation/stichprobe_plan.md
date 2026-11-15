# Vorab-Notiz: Stichprobe von Eckpunkten des Rasters gegen das Referenztool

Erstellt: 15.11.2026, VOR jedem Lauf des Referenztools mit diesen
Raketen, vor dem c_w-Scan und vor jedem Modellflug dieser Messung.
Zweck: KPI Tool-Vergleich (Teilfrage 1) für Kombinationen mehrerer
Parameter; Bericht 2.2, 3 und 4. Bisher sind nur R0 bis R9 gegen
das Referenztool geprüft, die je einen Parameter ändern.
Modellversion: "1". Repo-Stand bei Erstellung: 772de2c.

## 0. Vorab bekannt

- Tool-Vergleich R0 bis R9: 10 von 10 innerhalb S
  (tool_vergleich/results).
- Parameterstudie (parameterstudie/results/parameterstudie.md): je
  Eckrakete größtes Apogäum und f_max bei c_w = 0,345. Die
  Rohdaten (parameterstudie/data) enthalten auch die Modellwerte
  bei 33 % Füllstand mit c_w = 0,345; sie gelten als bekannt.
- Keine Werte des Referenztools für die Eckraketen.
- Kein c_w-Scan und kein Modellflug mit c_w' für die Eckraketen.

## 1. Auswahl der Eckraketen

Ecken des Rasters (parameterstudie_plan.md, Abschnitt 1): Flasche
1,0 l / 79 mm oder 2,0 l / 102 mm, Startdruck 3 oder 7 bar, Düse
15 oder 22 mm, Leermasse 100 oder 250 g, zusammen 16 Ecken.

Regel: je Flasche die beiden Extremkombinationen der übrigen
Faktoren, nämlich "7 bar, 22 mm, 100 g" und "3 bar, 15 mm, 250 g".
Jede Stufe jedes Faktors kommt damit genau zweimal vor. Die Regel
nutzt nur Parameterstufen, keine Messwerte.

| Nr. | Flasche        | Startdruck | Düse  | Leermasse | Wasser  |
|-----|----------------|------------|-------|-----------|---------|
| E1  | 1,0 l, 79 mm   | 7 bar      | 22 mm | 100 g     | 0,33 l  |
| E2  | 1,0 l, 79 mm   | 3 bar      | 15 mm | 250 g     | 0,33 l  |
| E3  | 2,0 l, 102 mm  | 7 bar      | 22 mm | 100 g     | 0,66 l  |
| E4  | 2,0 l, 102 mm  | 3 bar      | 15 mm | 250 g     | 0,66 l  |

Wassermenge: Füllstand 33 % (Rasterpunkt i = 28 der
Parameterstudie, nahe dem Drittel von R0). Alle Werte plausibel,
NICHT gemessen; Durchmesser 79 und 102 mm sind Anhaltswerte, nicht
zitierfähig.

Grenze der Auswahl: Druck, Düse und Leermasse ändern sich
gemeinsam. Eine Abweichung lässt sich daher keinem einzelnen Faktor
zuordnen; die Einzelwirkungen prüfen R1 bis R9.

Verworfen: ausgewogener Teilplan mit gekreuzter Flasche und
gekreuztem Druck (Extreme teilweise nicht enthalten); Zufallsauswahl
mit festem Startwert (Ränder können fehlen).

Modell (SI): v_bottle 1,0e-3 bzw. 2,0e-3 m³; d_body 0,079 bzw.
0,102 m; v_water0 0,33e-3 bzw. 0,66e-3 m³; p0_gauge 7e5 bzw.
3e5 Pa; d_nozzle 0,022 bzw. 0,015 m; m_empty 0,10 bzw. 0,25 kg;
temp0 Standard (293,15 K); ohne Geometrie.

## 2. c_w-Scan und Schwelle S

Je Eckrakete eine Vorwärtsserie über die API wie
cw_sensitivitaet_plan.md, Abschnitt 2: c_w von 0 bis 1,0 in 101
Schritten. Auswertung wie dort, Abschnitte 4 und 7:

    S = (h(0,30) - h(0,345)) / h(0,345)

h(0,345) linear zwischen 0,34 und 0,35 interpoliert. Beschreibend:
Re_max = v_burnout(0,345) * d_body / nu mit nu = 1,453e-5 m²/s;
über 2e5: Limitation.

## 3. KPI-Regel (unverändert aus dem Tool-Vergleich R0 bis R9)

- Modell: Einzelflug mit c_w' = 0,345 * 1,2039 / 1,225 (als Formel),
  temp0 Standard.
- Tool: h_Tool = (h(0,33) + h(0,36)) / 2, Standardform.
- Paar gültig, wenn beide Läufe fliegen und sich die Gesamtimpulse
  um höchstens 0,05 Ns unterscheiden. Sonst sofort Ersatzpaar 0,32
  und 0,37, gleiche Prüfung. Sonst "nicht auswertbar".
- d = (h_Modell - h_Tool) / h_Tool in %, mit Vorzeichen.
- Erfüllt, wenn |d| <= S der jeweiligen Eckrakete.
- Berichtet: Zahl der erfüllten Eckraketen von 4, Zahl der nicht
  auswertbaren, d und S je Eckrakete; beschreibend
  e = ((h(c1) + h(c2)) / 2 - h(0,345)) / h(0,345) aus dem Modellscan
  und Re_max.
- Nicht gemessen: Flaschenform (Delta_Form). Sie bleibt Limitation
  wie bei R0 bis R9.

## 4. Ablauf im Tool

Lokale Kopie vom 03.11.2026; Prüfsummen vorher gegen
sha256_2026-11-03.csv, bei Abweichung Abbruch. Ansicht "Advanced".
Felder getippt, Temperatur nur per Schieberegler. Nach jeder Eingabe
Tab, vor jedem Lauf "Run Simulation". Übrige Felder wie
tool_vergleich_plan.md, Abschnitt 2 (Grundeinstellung).

1. Reset to Default, Grundeinstellung R0 mit c_w 0.50. Anker A0:
   alle angezeigten Werte gleich Lauf 1 in
   tool_vergleich/data/tool_werte.csv, sonst Abbruch.
2. Je Eckrakete in der Reihenfolge E1 bis E4 immer alle sechs Felder
   setzen, auch wenn sie sich nicht ändern: Total Volume (1.00 bzw.
   2.00), Outside Diameter (79 bzw. 102), Water Amount (0.33 bzw.
   0.66), Pressure (7.00 bzw. 3.00), Nozzle Exit Diameter (22.0 bzw.
   15.0), Empty Mass (100 bzw. 250). Dann c_w 0.33 (Lauf), 0.36
   (Lauf). Ersatzpaar sofort, wenn das Paar nach Abschnitt 3
   ungültig ist.
3. Kontrolle K-E1: E1 erneut setzen, c_w 0.33 und 0.36. Alle Werte
   müssen den ersten E1-Läufen entsprechen. Sonst ist die Messung
   ungültig; Ursache suchen, vollständig wiederholen.
4. Vor jedem Lauf ein Screenshot, auf dem alle sechs Felder und c_w
   lesbar sind.

Liefert das Tool keinen Flug oder lehnt es einen Wert ab, gilt die
Eckrakete als "nicht auswertbar". Eingaben werden nicht angepasst.

Geplant: 11 Läufe (A0, 4 x 2, K-E1 x 2) plus Ersatzpaare.

## 5. Protokoll

experiments/stichprobe/data/tool_werte.csv: eine Zeile je Lauf in
der ausgeführten Reihenfolge; geplante Läufe sind vorab eingetragen,
Ersatzpaare werden angehängt. Werte wie angezeigt, Punkt als
Dezimalzeichen, ohne Einheiten. Anzeige "-" oder NaN: Feld leer,
Anzeige in "bemerkung". Ein Abschreibfehler darf nur korrigiert
werden, wenn der Lauf erneut gerechnet wurde (Vermerk in
"bemerkung").

experiments/stichprobe/data/tool_protokoll.md: Datum, Browser,
Prüfsummen, Ort der Screenshots, Auffälligkeiten.

## 6. Skripte und Ausgaben

Eigener Ordner experiments/stichprobe/ (Hilfsfunktionen kopiert,
Eckraketen per Test gegen Abschnitt 1 geprüft). Über die API (über
Nginx): je Eckrakete eine Rakete "Stichprobe Ex" mit c_w-Serie
(CSV-Export unverändert) und eine Rakete mit c_w' und einem
Einzelflug (JSON-Antwort unverändert). Skripte geben keine
Apogäen aus. Abbruch, wenn schon Daten vorhanden sind.
Rohdaten in data/ (CRLF), Auswertung in results/ (LF): Tabelle
(csv, md) und eine Abbildung (d je Eckrakete, S als Marke; PNG
300 dpi und SVG, Dezimalkomma).

## 7. Verfehlter KPI

Jede verfehlte Eckrakete wird unverändert berichtet, und die Ursache
wird untersucht (Modell, Tool-Eingabe, Tool-Ausreißer).

- Ist die Ursache bis 19.11.2026 eindeutig im Modell belegt:
  begründete Modelländerung, MODEL_VERSION "2", alle
  automatisierten Messungen neu (Werte des Referenztools bleiben
  gültig, sie hängen nicht vom Modell ab), beide Ergebnisse im
  Bericht.
- Sonst: Änderung nur als begründeter Vorschlag in Discussion und
  Future Work; keine neue Modellversion vor der Abgabe. Die
  Abweichung von der Results-Methodik-Schleife wird im Bericht
  offengelegt.

## 8. Reihenfolge

1. Diese Notiz und die Vorlage tool_werte.csv committen.
2. Skripte mit Tests committen.
3. c_w-Scan und Modellflüge, Rohdaten committen.
4. Tool-Läufe, tool_werte.csv und tool_protokoll.md committen.
5. Auswertung mit Tests committen, Werte erst danach ansehen.

Änderungen an dieser Notiz nur als datierter Nachtrag.
