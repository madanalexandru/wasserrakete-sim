# Vorab-Notiz: Vergleich mit dem Referenztool (R0 bis R9)

Erstellt: 10.11.2026, VOR jedem Lauf des Referenztools mit R0 bis R9
und vor jedem Modellflug dieser Messung.
Zweck: KPI Tool-Vergleich (Teilfrage 1, Bericht 2.2 und 3) nach
cw_sensitivitaet_plan.md, Abschnitte 7 und 8, mit einer Änderung
(Abschnitt 3 dieser Notiz).
Modellversion: "1".

Vorab bekannt: h(c_ref) des Modells je Rakete (kennzahlen.csv, seit
09.11. committet). Keine Werte des Referenztools für R0 bis R9 bei
c_w um 0,345. Aus dem Funktionstest bekannt: R0 bei c_w = 0,50 im
Tool (T3b, 49,57 m).

## 1. Vorprüfung am Referenztool (10.11.2026)

Rakete: Standardwerte des Tools nach "Reset to Default" (nicht im
Validierungssatz). Je Wert: Reset, c_w getippt, Tab, "Run
Simulation". Online-Seite.

| c_w   | Apogee (m) | Total Impulse (Ns) | Burn Time (s) |
|-------|------------|--------------------|---------------|
| 0.30  | 82.89      | 20.02              | 0.07          |
| 0.33  | 78.06      | 20.02              | 0.07          |
| 0.34  | 77.33      | 19.82              | 0.07          |
| 0.345 | 61.46      | 18.24              | 0.05          |
| 0.35  | -          | 0                  | 0             |
| 0.36  | 73.88      | 20.01              | 0.07          |
| 0.40  | 69.01      | 20.01              | 0.07          |
| 0.45  | 63.87      | 20.01              | 0.07          |
| 0.50  | 59.55      | 20.01              | 0.07          |

c_w = 0,345 ab Reset auch in der lokalen Kopie: gleiches Ergebnis
(61,46 m; 18,24 Ns).

Befund: Bei 0,34, 0,345 und 0,35 weicht der Gesamtimpuls ab, bei
0,35 fliegt die Rakete nicht. c_w wirkt auf den Luftwiderstand und
kaum auf den Schub; die Ursache im Tool ist unbekannt. Bei 0,34
liegt das Apogäum trotzdem zwischen den Nachbarwerten: Eine
Monotonieprüfung allein erkennt solche Läufe nicht, der Impuls schon.

## 2. Raketen und Abbildung auf das Tool

R0 bis R9 unverändert aus cw_sensitivitaet_plan.md, Abschnitt 1.
Das Tool erhält dieselben Nennwerte wie das Modell (Volumen
ungedehnt).

Grundeinstellung (R0): Outside Diameter 90 mm; Nozzle Exit Diameter
22.0 mm; Total Volume 1.50 L; Water Amount 0.50 L; Empty Mass 150 g;
Drag Coefficient je Lauf; Nozzle Adjuster A/B/C 14/16/44
(Standardform, "std") bzw. 0/0/50 (fast zylindrisch, "zyl"); Water
und Gas Thrust Efficiency 1; Pressure 5.00 bar; Launch Tube Diameter
0; Launch Tube Length 0; Launcher Volume 0.50 L (wie im
Funktionstest; Wirkung bei Rohrlänge 0 ungeklärt); Gas Source Air;
Liquid Density 1; Ambient Temperature 20 C (nur per Schieberegler);
Ambient Pressure 101325 Pa; Relative Humidity 0 %; Gravity 9.80665.

| Nr. | Änderung im Tool gegenüber R0              |
|-----|--------------------------------------------|
| R0  | keine                                      |
| R1  | Pressure 3.00                              |
| R2  | Pressure 7.00                              |
| R3  | Water Amount 0.30                          |
| R4  | Water Amount 0.70                          |
| R5  | Nozzle Exit Diameter 15.0                  |
| R6  | Empty Mass 100                             |
| R7  | Empty Mass 250                             |
| R8  | Total Volume 1.00, Outside Diameter 79     |
| R9  | Total Volume 2.00, Outside Diameter 102    |

Liefert das Tool keinen Flug oder lehnt es einen Wert ab, gilt die
Rakete in dieser Form als "nicht auswertbar". Eingaben werden dann
nicht angepasst.

## 3. Referenzwert des Tools (Änderung gegenüber dem c_w-Plan)

cw_sensitivitaet_plan.md (c_w-Plan), Abschnitte 7 und 8, sahen
h_Tool bei c_w = 0,345 vor. Wegen Abschnitt 1 dieser Notiz wird
h_Tool(0,345) stattdessen linear interpoliert, je Rakete und Form:

    h_Tool = (h(0,33) + h(0,36)) / 2

Gültigkeitsprüfung des Paars: Beide Läufe haben einen Flug, und die
Gesamtimpulse unterscheiden sich um höchstens 0,05 Ns. Die Grenze
liegt zwischen der Streuung normaler Läufe in Abschnitt 1 (0,01 Ns)
und dem kleinsten beobachteten Ausreißer (0,20 Ns).

Ist das Paar ungültig, wird sofort das Ersatzpaar 0,32 und 0,37
gerechnet (Mitte ebenfalls 0,345): h_Tool = (h(0,32) + h(0,37)) / 2,
gleiche Prüfung. Ist auch dieses ungültig: "nicht auswertbar".

Interpolationsfehler, berichtet ohne Schwelle: Abschätzung aus
Abschnitt 1 etwa 0,06 bis 0,08 m (rund 0,1 %). Je Rakete zusätzlich
aus dem Modellscan (Rasterpunkte vorhanden):
e = ((h(c1) + h(c2)) / 2 - h(c_ref)) / h(c_ref), mit dem verwendeten
Paar c1, c2 und h(c_ref) aus kennzahlen.csv.

Unverändert: Das Modell rechnet einen echten Flug mit
c_w' = 0,345 * 1,2039 / 1,225 (c_w-Plan, Abschnitt 8). S, die
KPI-Regel |h_Modell - h_Tool| / h_Tool <= S und Delta_Form bleiben
wie im c_w-Plan, Abschnitte 7 und 8; Delta_Form nutzt die
interpolierten Werte beider Formen.

## 4. Ablauf im Tool

Lokale Kopie vom 03.11.2026; Prüfsummen vorher gegen
sha256_2026-11-03.csv geprüft, bei Abweichung Abbruch. Ansicht
"Advanced". Felder getippt, Temperatur nur per Schieberegler. Nach
jeder Eingabe Tab, vor jedem Lauf "Run Simulation".

1. Reset to Default, Grundeinstellung mit c_w 0.50 (= T3b). Anker
   A0: Alle angezeigten Werte müssen T3b entsprechen (u. a. 49.57 m,
   14.14 Ns), sonst Abbruch.
2. Je Rakete in der Reihenfolge R0 bis R9: Änderung setzen; c_w 0.33
   (Lauf), 0.36 (Lauf); A/B/C 0/0/50; c_w 0.36 (Lauf), 0.33 (Lauf);
   A/B/C zurück auf 14/16/44; Änderung zurück auf R0. Ersatzpaar
   sofort, wenn ein Paar nach Abschnitt 3 ungültig ist.
3. Kontrolle K-R0: R0 Standardform bei 0.33 und 0.36 erneut. Alle
   Werte müssen den ersten R0-Läufen entsprechen. Sonst ist die
   Messung ungültig; Ursache suchen, vollständig wiederholen.

## 5. Protokoll

experiments/tool_vergleich/data/tool_werte.csv: eine Zeile je Lauf
in der ausgeführten Reihenfolge; geplante Läufe sind vorab
eingetragen, Ersatzpaare werden angehängt. Werte wie angezeigt,
Punkt als Dezimalzeichen, ohne Einheiten. Anzeige "-" oder NaN:
Feld leer, Anzeige in "bemerkung". Ein Abschreibfehler darf nur
korrigiert werden, wenn der Lauf erneut gerechnet wurde (Vermerk in
"bemerkung").

experiments/tool_vergleich/data/tool_protokoll.md: Datum, Browser,
Prüfsummen, Auffälligkeiten.

## 6. Modellflüge

Skript im Repo über die API (über Nginx), wie
experiments/cw_sensitivitaet/run.py: je Rakete eine neue Rakete
"Toolvergleich Rx" mit c_w = c_w' (als Formel, gleicher Wert wie
cw_strich in kennzahlen.csv) und temp0 als Standard (293,15 K), ein
Einzelflug, JSON-Antwort unverändert gespeichert, dazu eine
Übersicht. Keine Apogäen auf der Konsole. Abbruch, wenn schon Daten
vorhanden sind.

## 7. Auswertung

Skript mit Tests liest tool_werte.csv, die Modellflüge und
kennzahlen.csv (S unverändert). Je Rakete: h_Tool nach Abschnitt 3,
d = (h_Modell - h_Tool) / h_Tool in % mit Vorzeichen, erfüllt bei
|d| <= S; Delta_Form; e. Ausgabe: Tabelle (md, csv) und eine
Abbildung (d je Rakete, S als Marke; PNG 300 dpi und SVG).
Berichtet: Zahl der erfüllten Raketen von 10, Zahl der nicht
auswertbaren, d je Rakete. Verfehlte KPIs werden unverändert
berichtet.

## 8. Reihenfolge

1. Diese Notiz und die Vorlage tool_werte.csv committen.
2. Tool-Läufe (tool_werte.csv ausgefüllt) und tool_protokoll.md
   committen.
3. Modellflüge committen.
4. Auswertung: Tests vorher, Werte erst nach den Commits 1 bis 3
   ansehen.