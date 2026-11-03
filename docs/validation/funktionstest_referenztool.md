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