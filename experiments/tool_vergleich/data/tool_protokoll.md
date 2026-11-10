# Protokoll: Läufe im Referenztool (R0 bis R9)

Plan: docs/validation/tool_vergleich_plan.md

Datum: 10.11.2026
Browser/Version: [EINTRAGEN, chrome://version]
Tool-Version laut Seite: [EINTRAGEN]
Lokale Kopie: C:\Users\madan\Projekte\referenztool\2026-11-03
Prüfsummen gegen sha256_2026-11-03.csv: 16 Dateien, 0 Abweichungen
Anker A0 wie T3b: JA (Lauf 1; nach Reset wiederholt, Lauf 47)
Kontrolle K-R0 gleich den ersten R0-Läufen: JA (Läufe 42, 43)
Ersatzpaare gerechnet für: R1 zyl (Läufe 44, 45)
Nicht auswertbar: R1 zyl (Plan, Abschnitt 3)
Screenshots: [ORT EINTRAGEN ODER "nicht gespeichert"]

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