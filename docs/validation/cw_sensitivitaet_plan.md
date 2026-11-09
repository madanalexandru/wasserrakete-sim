# Vorab-Notiz: c_w-Sensitivität des Apogäums

Erstellt: 08.11.2026, VOR jeder Rechnung dieser Messung.
Zweck: Grundlage für die KPI-Schwellen der Validierung gegen das
Referenztool (Teilfrage 1, Bericht 2.2 und 3).
Modellversion: "1" (app/physics/ und app/search/ unverändert).

## 1. Raketen (Validierungssatz)

Alle Werte plausibel, NICHT gemessen. R8/R9: Durchmesser als
Anhaltswert (Mittelwert einer KI-Zusammenfassung, Primärquelle
ungeprüft, nicht zitierfähig). Dieselben 10 Raketen werden später
im Referenztool gerechnet; der Satz wird nach der Messung nicht
mehr geändert.

Basis R0: v_bottle 1,5e-3 m³; v_water0 0,5e-3 m³; p0_gauge 5e5 Pa;
d_nozzle 0,022 m; m_empty 0,15 kg; d_body 0,09 m; temp0 Standard
(293,15 K); ohne Geometrie. Jede Variante ändert nur die genannten
Werte:

| Nr. | Änderung gegenüber R0          |
|-----|--------------------------------|
| R0  | keine                          |
| R1  | p0_gauge 3e5 Pa                |
| R2  | p0_gauge 7e5 Pa                |
| R3  | v_water0 0,3e-3 m³             |
| R4  | v_water0 0,7e-3 m³             |
| R5  | d_nozzle 0,015 m               |
| R6  | m_empty 0,10 kg                |
| R7  | m_empty 0,25 kg                |
| R8  | v_bottle 1,0e-3 m³, d_body 0,079 m |
| R9  | v_bottle 2,0e-3 m³, d_body 0,102 m |

Gespeicherter c_w der Rakete: 0,5 (ohne Bedeutung, jede Serie
überschreibt c_w).

Vorab bekannt: Apogäum von R0 bei c_w = 0,5 wurde am 06.11.
versehentlich gesehen (Flug 16). Kein Vergleich mit dem
Referenztool vor der KPI-Festlegung.

## 2. Serie

Je Rakete eine Vorwärtsserie über die API: param_name c_w,
param_start 0, param_stop 1,0, n_steps 101 (Abstand 0,01;
Werte exakt i/100). c_w = 0 ist der widerstandsfreie Anker.

## 3. Unsicherheitsband und Referenzwert

Regel A: Band [c_min, c_max] = in Perotti et al. (2009) angegebene
Spanne gemessener c_w-Werte von Wasserraketen (bei einem Einzelwert
mit Unsicherheit: Wert ± Unsicherheit); c_ref = dort genannter
zentraler Wert. Quelle: Eur. J. Phys. 30, 1039–1048, zitiert nach
Romanelli et al. (2013), Ref. 5; Original noch nicht geprüft.

Fallback B (falls Perotti nicht beschaffbar): Band [0,05; 0,40],
c_ref = 0,225 (Bandmitte). 0,05 = eigene Umrechnung aus Finney
(2000, S. 224) mit Annahme d = 0,1 m (S. 227); 0,40 = Kugel nach
Timmerman & van der Weele (1999, S. 538). Keine dieser Quellen
misst Wasserraketen.

Werte zwischen Rasterpunkten: lineare Interpolation zwischen den
beiden Nachbarpunkten.

## 4. Auswertungsgrößen (je Rakete)

Hauptgröße: Delta_cw = (h(c_min) - h(c_max)) / h(c_ref) in %.

Zusatzgröße: Elastizität
eps = [(h(c_ref + 0,01) - h(c_ref - 0,01)) / 0,02] * c_ref / h(c_ref).

Abgeleitet (Luftdichte): Im Modell wirkt rho_Luft nur über
k = 0,5 * rho * c_w * A. Effekt der Tool-Dichte daher
(h(c_ref * 1,2039 / 1,225) - h(c_ref)) / h(c_ref) in %
(1,2039 kg/m³ aus Rückrechnung, siehe projektlog).

Die KPI-Schwellen werden erst NACH dieser Messung festgelegt.
Bewertung Luftdichte und Flaschenform: nach der Messung, vor dem
Vergleich mit dem Referenztool; Regel wird gesondert festgelegt.

## 5. Darstellung

Eine Abbildung: h / h(c_ref) über c_w, eine Kurve je Rakete, Band
grau hinterlegt. Eine Tabelle: Delta_cw, eps, Luftdichte-Effekt je
Rakete.

## 6. Durchführung und Reproduzierbarkeit

Python-Skript im Repo (nur Standardbibliothek) legt die Raketen an,
startet die Serien über die API (über Nginx) und speichert jeden
CSV-Export unverändert unter experiments/cw_sensitivitaet/data/.
Das Skript gibt keine Apogäen aus. Ein zweites Skript berechnet
Abschnitt 4 und erzeugt Abbildung und Tabelle aus den CSV-Dateien.
Die Werte werden erst angesehen, wenn diese Notiz committet ist.

## 7. Nachtrag vom 09.11.2026 (vor Ansicht der Werte)

Stand: Messdaten committet (f289bec). Die Apogäen hat noch niemand
angesehen; alle Prüfungen gaben nur Ja/Nein und Zählungen aus.
Die Abschnitte 1 bis 6 bleiben unverändert stehen.

Quelle beschafft und im Original geprüft: Barrio-Perotti, R.,
Blanco-Marigorta, E., Argüelles-Díaz, K. & Fernández-Oro, J.
(2009), Eur. J. Phys. 30, 1039–1048, doi:10.1088/0143-0807/30/5/012.
In Abschnitt 3 war der Erstautor verkürzt als "Perotti" genannt.
Damit gilt Regel A; Fallback B entfällt.

Befund: Die Quelle nennt c_w = 0,345 ± 0,004 für eine einzige
2-l-Rakete (D = 106,0 mm; S. 1045, S. 1047 Gl. 6), gültig für
1e3 < Re < 2e5 (S. 1047). ± 0,004 ist die Messgenauigkeit dieses
Versuchs (S. 1047, Tab. 1), nicht die Streuung zwischen Raketen.
Unsere Raketen R0 bis R9 sind nicht gemessen; für die KPI-Schwelle
zählt daher die Unsicherheit eines ungemessenen c_w.

Änderung: Ausgewertet werden zwei Bänder, beide mit c_ref = 0,345.
- Messband (Regel A wörtlich): [0,341; 0,349]. Wird berichtet
  (Discussion), begründet aber keine Schwelle.
- Formband: [0,30; 0,47]. 0,30 = torpedoförmiger Körper
  (Timmerman & van der Weele 1999, S. 544); 0,47 = Kugel
  (Barrio-Perotti et al. 2009, S. 1045, nach White 1999).
Abschnitt 4 (Delta_cw je Band, eps, Luftdichte-Effekt) wird bei
c_ref = 0,345 ausgewertet; c_ref ± 0,01 und Bandgrenzen zwischen
Rasterpunkten werden linear interpoliert.

Regel für die KPI-Schwelle (Vergleich mit dem Referenztool):
S = (h(0,30) - h(0,345)) / h(0,345) je Rakete, also die
Apogäumsänderung, wenn c_w vom Referenzwert auf die nähere Grenze
des Formbands fällt. Der KPI gilt für eine Rakete als erfüllt, wenn
|h_Modell - h_Tool| / h_Tool <= S, beide gerechnet mit c_w = 0,345.
Berichtet wird die Zahl der erfüllten Raketen von 10 und je Rakete
die Abweichung. Die Regel für Luftdichte und Flaschenform wird
gesondert festgelegt, ebenfalls vor Ansicht der Werte.

Zusätzlich auszuwerten: maximale Reynoldszahl je Rakete bei
c_ref, Re = v_burnout * d_body / nu mit nu = 1,453e-5 m²/s
(Barrio-Perotti et al. 2009, S. 1044). Liegt sie über 2e5, ist das
eine Limitation (c_w-Wert außerhalb seines Gültigkeitsbereichs).