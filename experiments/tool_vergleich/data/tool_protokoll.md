# Protokoll: Läufe im Referenztool (R0 bis R9)

Plan: docs/validation/tool_vergleich_plan.md

Datum: 10.11.2026
Browser/Version: siehe Nachtrag vom 16.11.2026
Tool-Version laut Seite: siehe Nachtrag vom 16.11.2026
Lokale Kopie: C:\Users\madan\Projekte\referenztool\2026-11-03
Prüfsummen gegen sha256_2026-11-03.csv: 16 Dateien, 0 Abweichungen
Anker A0 wie T3b: JA (Lauf 1; nach Reset wiederholt, Lauf 47)
Kontrolle K-R0 gleich den ersten R0-Läufen: JA (Läufe 42, 43)
Ersatzpaare gerechnet für: R1 zyl (Läufe 44, 45)
Nicht auswertbar: R1 zyl (Plan, Abschnitt 3)
Screenshots: siehe Nachtrag vom 16.11.2026

## Auffälligkeiten

- R1 zyl: NaN bei c_w 0,36 (Lauf 8) und im Ersatzpaar bei 0,37
  (Lauf 45). Damit nicht auswertbar; R1 std ist gültig.
- Ablaufabweichung: Ersatzpaar R1 zyl erst nach Lauf 13 statt
  sofort gerechnet (Anleitung hatte die Sofort-Regel nicht
  wiederholt). K-R0 zeigt reproduzierbares Rechnen des Tools.
- Lauf 46 (R1 zyl, c_w 0,39): nicht im Plan, nicht ausgewertet.
- Reset nach Lauf 46; Grundeinstellung neu gesetzt, Anker
  wiederholt (Lauf 47), gleich A0.
- R8/R9: Outside Diameter 79 bzw. 102 laut Durchführendem
  eingestellt; in den Screenshots nicht sichtbar.
- Nozzle Exit Diameter teils als "22" statt "22.0" eingegeben
  (gleicher Wert).

## Nachtrag vom 16.11.2026: Browser, Tool-Version, Screenshots

Die drei Felder oben waren am 10.11. leer geblieben und wurden am
16.11. nachgetragen.

- Browser/Version: am 10.11. nicht notiert. Laut chrome://version am
  04.11. und am 15.11.: Google Chrome 156.0.8078.48 (Offizieller
  Build) (64-Bit), Windows 11 Version 25H2 (Build 26200.9711).
- Tool-Version laut Seite: Fußzeile der lokalen Kopie 2026-11-03
  „Copyright © 2002-2016 Dean Wheeler - Ported to JavaScript by
  George Katz - V0.4 2017-2020“ (Screenshot vom 15.11.). Die Kopie
  war am 10.11. unverändert (Prüfsummen oben: 0 Abweichungen).
- Screenshots: C:\Users\madan\Pictures\Screenshots, Dateien mit
  Änderungsdatum 10.11.2026 (68 PNG; nicht geprüft, ob alle zu den
  Läufen gehören). Nicht einzeln den Läufen zugeordnet, nicht im Repo.