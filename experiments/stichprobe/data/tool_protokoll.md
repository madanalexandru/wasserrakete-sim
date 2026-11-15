# Protokoll: Läufe im Referenztool (Stichprobe E1 bis E4)

Plan: docs/validation/stichprobe_plan.md

Datum: 15.11.2026
Browser/Version: Google Chrome 156.0.8078.48 (Offizieller Build) (64-Bit), Windows 11 Version 25H2 (Build 26200.9711)
Lokale Kopie: C:\Users\madan\Projekte\referenztool\2026-11-03
Prüfsummen gegen sha256_2026-11-03.csv: 0 Abweichungen (laut Durchführendem)
Anker A0 wie Lauf 1 im Tool-Vergleich R0 bis R9: JA (Lauf 1)
Kontrolle K-E1 gleich den ersten E1-Läufen: JA (Läufe 10 und 12)
Ersatzpaare gerechnet für: keine (alle vier Paare |ΔI| <= 0,05 Ns)
Nicht auswertbar: keine

## Auffälligkeiten

- Total Volume als "1" bzw. "2" statt "1.00"/"2.00" eingegeben; Nozzle teils als "22"/"15" statt "22.0"/"15.0" (gleicher Wert).
- Lauf 11: Eingabefehler (Water Amount 0.36 statt Drag 0.36), Kontrolllauf K-E1 bei 0.36 als Lauf 12 wiederholt. Zeilen 11/12 der Vorlage deshalb angepasst.