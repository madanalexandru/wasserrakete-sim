# Algorithmenvergleich (inverser Modus, 40 Zielhöhen je Serie)

K1 (konvergiert): 30 von 30 Serien.
K2 (delta <= S/100): 1200 von 1200 Suchen.
H1 (binär = 22): 400 von 400 Suchen.
H2 (exponentiell nach Tabelle): 400 von 400 gewerteten Suchen; 0 Grenzfälle getrennt.
H3 (Interpolation, Median < 22): 10 von 10 Raketen.
Zeit invers: 30 von 30 Serien mit t_Client < 300 s.
Aufwand invers: 30 von 30 Serien mit höchstens 3 Aufrufen.

## Auswertungen je Suche: Median (Min. bis Max.)

| Rakete | binär | exponentiell | Interpolation | delta max. in % | S/100 in % |
|---|---|---|---|---|---|
| R0 | 22 (22 bis 22) | 25 (19 bis 25) | 8 (6 bis 10) | 0,00066 | 0,05101 |
| R1 | 22 (22 bis 22) | 25 (19 bis 25) | 8 (6 bis 10) | 0,00066 | 0,03339 |
| R2 | 22 (22 bis 22) | 25 (19 bis 25) | 8 (6 bis 10) | 0,00066 | 0,06304 |
| R3 | 22 (22 bis 22) | 25 (19 bis 25) | 8 (6 bis 8) | 0,00076 | 0,04901 |
| R4 | 22 (22 bis 22) | 25 (21 bis 25) | 8 (7 bis 11) | 0,00115 | 0,04697 |
| R5 | 22 (22 bis 22) | 25 (19 bis 25) | 8 (6 bis 9) | 0,00072 | 0,04984 |
| R6 | 22 (22 bis 22) | 23 (19 bis 25) | 9,5 (7 bis 12) | 0,00143 | 0,07139 |
| R7 | 22 (22 bis 22) | 25 (21 bis 25) | 7 (6 bis 9) | 0,00051 | 0,02568 |
| R8 | 22 (22 bis 22) | 25 (21 bis 25) | 8 (6 bis 11) | 0,00092 | 0,03073 |
| R9 | 22 (22 bis 22) | 24 (19 bis 25) | 8 (7 bis 10) | 0,00063 | 0,06527 |

## Summe der Auswertungen und Zeiten je Verfahren

| Verfahren | Auswertungen gesamt | t_Client in s: Median (Min. bis Max.) |
|---|---|---|
| binary | 8800 | 37,5 (30,6 bis 77,3) |
| exponential | 9474 | 43,2 (33,1 bis 87,9) |
| interpolation | 3185 | 15,1 (12,1 bis 29,7) |
