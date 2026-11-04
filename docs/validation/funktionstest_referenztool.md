# Funktionstest Referenztool

## Vorab-Notiz (vor dem Test festgelegt, 03.11.2026)

Referenztool: Air Command Water Rocket Simulator, JavaScript-Port des
Modells von D. Wheeler.
URL: http://www.aircommandrockets.com/sim/simulator.htm

Vorgehen: reiner Funktionstest. Geprüft werden: Das Tool läuft, die
Eingaben sind abbildbar, die Ausgaben sind dokumentiert, offene Punkte
werden geklärt, und die Plausibilität wird nur innerhalb des Tools geprüft.

Kein Zahlenvergleich mit dem eigenen Modell. Der erste Vergleich folgt
in Phase 4, direkt nachdem die c_w-Sensitivität gemessen und die KPIs
festgelegt sind.

Erwartungen für die Plausibilitätsprüfung (jeweils nur ein Wert geändert):
- Startdruck 4 / 5 / 6 bar: Apogäum steigt mit dem Druck.
- Wirkungsgrade 0,97 statt 1: Apogäum niedriger.
- Relative Luftfeuchte 50 % statt 0 %: Apogäum leicht höher
  (Wheeler, Modeling the Thrust Phase, Anhang B).

## Durchführung

Datum/Uhrzeit: 03.11.2026 15:55
Browser/Version: Google Chrome 156.0.8078.48 (Offizieller Build, 64-Bit), JavaScript V8 15.6.75.19, Windows 11 25H2 (Build 26200.9711)
Versionsangabe auf der Seite: Copyright © 2002-2016 Dean Wheeler - Ported to JavaScript by George Katz - V0.4 2017-2020
Prüfsummen: sha256_2026-11-03.csv (lokal, nicht im Repo)

## T2 Standardwerte (nach "Reset to Default", Ansicht "Advanced")

Rocket: Outside Diameter 105 mm; Nozzle Exit Diameter 22.0 mm;
Total Volume 2.10 L; Water Amount 0.50 L; Empty Mass 100 g;
Drag Coefficient 0.50; Nozzle Adjuster A 14, B 16, C 44;
Water Thrust Efficiency 0.97; Gas Thrust Efficiency 0.97.

Launcher: Pressure 7.00 bar (Anzeige daneben: 101 psi);
Launch Tube Diameter 0 mm; Launch Tube Length 0 mm;
Launcher Volume 0.50 L; Gas Source Air; Liquid Density 0.997 g/cm^3.

Environment: Ambient Temperature 25 C; Ambient Pressure 101325 Pa;
Relative Humidity in Rocket 100 %; Gravity 9.807 m/s2.

Voreinstellungen: Standard, Advanced, Dark Shadow, Charlie, Reset to Default.

Ergebnis mit Standardwerten (online und gespeicherte Kopie identisch):
Burnout 0.08 s, 4.36 m, 78.05 m/s, -16.92 G;
Thrust: Total Impulse 20.01 Ns, Burn Time 0.07 s, Peak 545.83 N,
Average 295 N, Motor Equivalent E295;
Apogee 2.73 s, 59.55 m; Crashdown 7.13 s, -19.09 m/s.

Kopie auch ohne Internet geprüft: gleiches Ergebnis.

## T3 Beispielrakete (Eingaben laut Abbildungstabelle, in der Kopie)
Eingaben vom Tool unverändert übernommen (auch Gravity 9.80665).
Anzeige neben Pressure 5 bar: 72 psi.
Auffällig: In der gespeicherten Kopie erscheinen alle Schieberegler doppelt.

| Ergebnis | Lauf 1 | Lauf 2 |
|---|---|---|
| Burnout Time | NaN | NaN |
| Burnout Altitude | NaN | NaN |
| Burnout Velocity | NaN | NaN |
| Burnout Acceleration | -1.00 G | -1.00 G |
| Total Impulse | NaN | NaN |
| Burn Time | 0.05 s | 0.05 s |
| Peak Thrust | 387.81 N | 387.81 N |
| Average Thrust | 284 N | 284 N |
| Motor Equivalent | A284 | A284 |
| Apogee Time | NaN | NaN |
| Apogee Altitude | NaN | NaN |
| Crashdown Time | NaN | NaN |
| Crashdown Velocity | NaN | NaN |

Ursachensuche: siehe T3-Diagnose.

## T3-Diagnose (ausgehend von T3, jeweils nur eine Änderung)
| Lauf | Änderung | Apogee Altitude |
|---|---|---|
| D0 | gleiche Eingaben, ONLINE-Seite | NaN |
| D1 | Humidity 1 % statt 0 % | NaN |
| D2 | Humidity 0 %, Wirkungsgrade 0.99 statt 1 | NaN |
| D3 | wie T3, Gravity 9.807 | NaN |

Konsole (F12): "calculations done" aus compressed.js, keine Rechenfehler-Meldung.
Sonstige Meldungen: fehlende Symbol-Schriftarten (glyphicons), Hinweis
plotly-latest = v1.58.5. Beides ohne Einfluss auf die Rechnung.
Bewertung: D0-D3 schließen eine Ursache NICHT aus, falls mehrere Auslöser
gleichzeitig wirken. Daher kumulative Reihe ab Standardwerten.

## T3-Diagnose kumulativ (ab Reset to Default, Änderungen bleiben stehen)
| Lauf | zusätzliche Änderung | Apogee Altitude |
|---|---|---|
| K0 | keine (Standardwerte) | 59.55 |
| K1 | Humidity 0 | 59.16 |
| K2 | Wirkungsgrade 1 | 59.97 |
| K3 | Pressure 5 | 50.40 |
| K4 | Outside Diameter 90 | 60.87 |
| K5 | Total Volume 1.5 | 51.56 |
| K6 | Empty Mass 150 | 49.89 |
| K7 | Liquid Density 1 | 49.87 |
| K8 | Ambient Temperature 20 | NaN |
| K9 | Gravity 9.80665 | nicht ausgeführt (Abbruch bei K8) |

Erster Auslöser: K8 (Ambient Temperature 25 -> 20 C), Ergebnis NaN.
Burn Time 0.05 s und Peak Thrust 387.81 N werden noch angezeigt.

## T3-Diagnose Temperatur
| Lauf | Zustand | Apogee Altitude |
|---|---|---|
| E1 | wie K8, aber Humidity 100 | NaN |
| E2 | wie K8, aber Temperature 21 | NaN |
| E3 | wie K8, aber Temperature 19 | NaN |
| E4 | Standardwerte, nur Temperature 20 | NaN |

Eigene Beobachtung: Nach Reset to Default rechnet das Tool normal. Sobald
Ambient Temperature von 25 auf einen anderen Wert geändert wird, Ergebnis NaN.
Auch erneutes Eintippen von 25 behebt das nicht; nur Reset to Default.
Bewertung: vermutlich Fehler in der Eingabeverarbeitung, nicht Wertebereich.

## T3-Diagnose Eingabeweg Temperatur
| Lauf | Vorgehen | Apogee Altitude |
|---|---|---|
| S1 | Reset, Temperatur nur per Schieberegler auf 20 | 58.83 |
| S2 | Reset, 25 ins Feld tippen (gleicher Wert), Tab | 59.55 |

Eigene Beobachtungen: Reset, 25 löschen und erneut 25 tippen -> normal.
Danach Änderung per Schieberegler -> normal.
Reset, 25 löschen und anderen Wert tippen -> NaN.
Bewertung (Vermutung): Fehler nur bei getippter Änderung des
Temperaturfeldes; Schieberegler funktioniert. Gleicher Wert löst kein
Änderungsereignis aus. Workaround: Temperatur nur per Schieberegler.

## T3 wiederholt (Temperatur per Schieberegler)
| Ergebnis | T3b (Pressure getippt) | T3c (Pressure per Regler) |
|---|---|---|
| Burnout Time | 0.07 s | 0.07 s |
| Burnout Altitude | 1.87 m | 1.87 m |
| Burnout Velocity | 42.76 m/s | 42.76 m/s |
| Burnout Acceleration | -3.38 G | -3.38 G |
| Total Impulse | 14.14 Ns | 14.14 Ns |
| Burn Time | 0.06 s | 0.06 s |
| Peak Thrust | 386.04 N | 386.04 N |
| Average Thrust | 222 N | 222 N |
| Motor Equivalent | D222 | D222 |
| Apogee Time | 2.89 s | 2.89 s |
| Apogee Altitude | 49.57 m | 49.57 m |
| Crashdown Time | 6.41 s | 6.41 s |
| Crashdown Velocity | -23.48 m/s | -23.48 m/s |

T3b und T3c identisch.

## T4 Offene Punkte
a) Druck 0: Eingabe 0 wird automatisch auf 1 gesetzt (Minimum 1 bar).
Test mit 1 bar: Apogee 7.34 m, Peak Thrust 73.83 N, Burnout 0.14 s.
Folgerung: Eingabe ist Überdruck (bei Absolutdruck läge 1 bar unter
dem Umgebungsdruck, kein Schub möglich).
b) Schub endet bei: ca. 0.07 s (Hover: 0.145 N bei t = 0.0718 s). Zwei Abschnitte:
Wasserschub mit Anstieg 0 -> ca. 386 N in ca. 0.006 s, danach fallend,
kurz vor ca. 0.047 s Abfall auf nahe 0; anschließend Luftstoß mit Sprung
auf ca. 125 N, abklingend bis ca. 0.07 s. Burnout (0.07 s) = Ende
Luftstoß. Burn Time (0.06 s) entspricht keinem der beiden Enden
(Definition unklar). Hover zeigt Werte mit 7-8 Stellen.
Werte mit "ca." aus dem Diagramm abgelesen.
c) Luftdichte/Dehnung sichtbar: kein Feld. Rückrechnung aus Burnout-Werten (Leermasse, c_w, Durchmesser,
Geschwindigkeit, Verzögerung): Standard 25 C -> 1.1839 kg/m3, T3b 20 C ->
1.2039 kg/m3; ideales Gas aus T und p: 1.1839 bzw. 1.2041 kg/m3.
Folgerung: Tool berechnet Luftdichte vermutlich aus Umgebungstemperatur
und -druck. Dehnung: kein Feld; Standardvolumen 2.10 L deutet auf Eingabe
des gedehnten Volumens hin (Indiz).
d) Nozzle Adjuster Standard (A, B, C): 14, 16, 44
   erlaubte Werte: A 0 - 50; B 0 - 50; C 0 - 50.
   Beobachtung: A und B verändern Schulter und Halslänge, C rundet die
   Schulter. Exakte Bedeutung undokumentiert (von Wheeler definierte
   Formparameter).
   zylindrisch (A, B, C): nicht exakt einstellbar; nächstliegende Form: A=0, B=0, C=50
   (fast zylindrisch, kurzer schmaler Stummel an der Düse bleibt)

## T5 Plausibilität
| Änderung (sonst wie T3b) | Apogee Altitude |
|---|---|
| Druck 4 bar | 41.15 m |
| Druck 6 bar | 57.07 m |
| Wirkungsgrade 0,97 | 48.55 m |
| Feuchte 50 % | 49.76 m |

Alle drei vorab festgelegten Erwartungen erfüllt.
Kontrolle nach Rückstellung: 49.57 m.

## T6 Flaschenform
Apogäum Standardform (A/B/C = 14/16/44, aus T3b): 49.57 m
Apogäum fast zylindrisch (A/B/C = 0/0/50): 49.39 m
Unterschied: -0.18 m. Bewertung erst in Phase 4 (Vergleich mit
c_w-Sensitivität, Option C).