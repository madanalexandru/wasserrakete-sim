# Durchsatz vorwärts (1000 Schritte je Serie)

KPI Zeit: 30 von 30 Serien mit t_Client < 300 s.
KPI Aufwand: 30 von 30 Serien mit höchstens 3 Aufrufen.

Median (Min. bis Max.) über die Durchgänge. D in Flügen/s.

| Rakete | t_Client in s | D_Client | D_Server | Aufrufe max. | Zeit | Aufwand |
|---|---|---|---|---|---|---|
| R0 | 63,3 (60,5 bis 65,4) | 15,8 (15,3 bis 16,5) | 15,8 (15,3 bis 16,5) | 3 | ja | ja |
| R1 | 66,8 (64,1 bis 68,8) | 15,0 (14,5 bis 15,6) | 15,0 (14,5 bis 15,6) | 3 | ja | ja |
| R2 | 64,8 (64,6 bis 70,4) | 15,4 (14,2 bis 15,5) | 15,4 (14,2 bis 15,5) | 3 | ja | ja |
| R3 | 51,3 (48,5 bis 53,9) | 19,5 (18,6 bis 20,6) | 19,5 (18,6 bis 20,6) | 3 | ja | ja |
| R4 | 82,6 (81,9 bis 85,2) | 12,1 (11,7 bis 12,2) | 12,1 (11,7 bis 12,2) | 3 | ja | ja |
| R5 | 136,9 (131,0 bis 157,8) | 7,3 (6,3 bis 7,6) | 7,3 (6,3 bis 7,6) | 3 | ja | ja |
| R6 | 64,8 (61,9 bis 65,3) | 15,4 (15,3 bis 16,2) | 15,4 (15,3 bis 16,2) | 3 | ja | ja |
| R7 | 70,0 (62,3 bis 78,3) | 14,3 (12,8 bis 16,0) | 14,3 (12,8 bis 16,0) | 3 | ja | ja |
| R8 | 59,1 (59,1 bis 71,6) | 16,9 (14,0 bis 16,9) | 16,9 (14,0 bis 16,9) | 3 | ja | ja |
| R9 | 72,6 (72,1 bis 112,9) | 13,8 (8,9 bis 13,9) | 13,8 (8,9 bis 13,9) | 3 | ja | ja |

## Monotonie Apogäum(Startdruck), 1 kPa bis 1000 kPa

M1: keine Abnahme zwischen Nachbarn. M2: streng steigend ab dem
ersten Apogäum > 0. Ausschluss aus dem Algorithmenvergleich nur bei
M2 = nein (Nachtrag 2).

| Rakete | M1 | M2 | Abnahmen | davon zwischen Apogäen <= 0 | im Vergleich |
|---|---|---|---|---|---|
| R0 | nein | ja | 6 | 6 | ja |
| R1 | nein | ja | 6 | 6 | ja |
| R2 | nein | ja | 6 | 6 | ja |
| R3 | nein | ja | 5 | 5 | ja |
| R4 | nein | ja | 9 | 9 | ja |
| R5 | nein | ja | 10 | 10 | ja |
| R6 | nein | ja | 6 | 6 | ja |
| R7 | nein | ja | 9 | 9 | ja |
| R8 | nein | ja | 8 | 8 | ja |
| R9 | nein | ja | 7 | 7 | ja |
