# Vorab-Notiz: übrige KPIs (analytisch, Durchsatz, Algorithmen)

Erstellt: 10.11.2026, VOR jeder Messung dieser KPIs.
Zweck: Bericht 2.2; Teilfragen 1 bis 3.
Modellversion: "1". Repo-Stand bei Erstellung: 55ab311.
Raketen: Validierungssatz R0 bis R9 (wie cw_sensitivitaet_plan.md).
Schwellen S je Rakete: Spalte S_pct in
experiments/cw_sensitivitaet/results/kennzahlen.csv (volle
Genauigkeit; gerundet: R0 5,10; R1 3,34; R2 6,30; R3 4,90; R4 4,70;
R5 4,98; R6 7,14; R7 2,57; R8 3,07; R9 6,53 %).

## 0. Vorab bekannt

- Tests grün (Beispielrakete): Freiflug ohne/mit Widerstand
  abs. 1e-9 m; Raketengleichung mit Suche rel. 1e-6; Gesamtmodell
  c_w = 0 ab Brennschluss abs. 1e-4 m. Ausgang von KPI 1 ist damit
  für R0 weitgehend vorhersehbar.
- Sandbox-Sonde (kein Messwert): 0,04 bis 0,08 s pro Flug.
- Sandbox-Sonde (kein Messwert): Monotonie Apogäum(Startdruck)
  für die Beispielrakete 0,1 bis 10 bar ohne Verletzung.
- Auswertungszahlen von binärer und Exponentialsuche hängen nur von
  der Lage des gesuchten Drucks p* ab, nicht von der Kurvenform.
  Sandbox, Ersatzfunktion f(p) = p, P_MIN 1 kPa, P_MAX 1000 kPa,
  tol 1 Pa, step0 50 kPa (nicht im Repo):
  binär immer 22; exponentiell 18 bis 25 (Tabelle in Abschnitt 3).
- h(c_ref) je Rakete (kennzahlen.csv, seit 09.11. committet).
- Keine Werte für die Kennzahlen dieser Notiz.

## 1. KPI analytische Lösung (Teilfrage 1, Entscheidung 95 A2)

Kennzahl: eps = |h_Modell - h_ana| / h_ana je Rakete.

F1, Freiflug ohne Widerstand ab Brennschluss: Rakete mit c_w = 0,
ein Einzelflug über die API.
h_ana = h_burnout + v_burnout^2 / (2 g)
(Timmerman & van der Weele 1999, S. 539, Gl. 9).

F2, Freiflug mit Widerstand ab Brennschluss: Rakete mit
c_w = 0,345 (c_ref), ein Einzelflug über die API.
h_ana = h_burnout + m/(2k) * ln(1 + k v_burnout^2 / (m g))
mit m = m_empty + 1000 kg/m^3 * water_rest,
k = 0,5 * 1,225 kg/m^3 * c_w * pi d_body^2 / 4
(ebd., S. 542, Gl. 33; Umformung von Hand, Auftrieb vernachlässigt).

Schwelle: eps <= S/100 je Rakete (für R7 also 0,0257 %).
Begründung: Der numerische Fehler soll mindestens zwei
Größenordnungen unter der c_w-Unsicherheit liegen, damit beide
Fehlerquellen getrennt bleiben. Der Faktor 100 ist eine Konvention.
Berichtet: eps je Rakete und Fall; Anzahl erfüllt von 10 je Fall.
v_burnout <= 0 oder Fehler -> "nicht auswertbar".

Nicht Teil des KPI: Wasserphase nur im Grenzfall konstanten Drucks
(bestehender Test, Beispielrakete; Restabweichung ca. 1e-7 ungeklärt).
Luftstoß ohne analytische Lösung -> Limitation.

## 2. KPI Durchsatz und Serienaufwand (Teilfrage 2, Entscheidung 96 B1)

"Groß" = die eigenen Obergrenzen: 1000 Schritte vorwärts
(SERIES_MAX_STEPS), 40 Schritte invers (SERIES_MAX_STEPS_INVERSE).

Durchsatz in Flügen/s, zweimal:
- D_Server = Flüge / duration_s (Definition 23b).
- D_Client = Flüge / t_Client, t_Client = time.perf_counter() um den
  POST der Serie über Nginx (inkl. Vorabprüfung und Commit).

Aufwand: Anzahl HTTP-Aufrufe für Definieren, Rechnen, Speichern und
Exportieren einer Serie (vom Skript gezählt).

Messung vorwärts: je Rakete (c_w = 0,345) eine Serie p0_gauge von
1 kPa bis 1000 kPa, 1000 Schritte. Ein Aufwärmlauf (nicht gewertet),
dann 3 Durchgänge über alle 10 Raketen. Berichtet: Median, Minimum,
Maximum je Rakete. Messung invers: Zeiten der 30 Serien aus
Abschnitt 3.

Schwellen:
- Jede Vorwärtsserie in jedem Durchgang: t_Client < 300 s
  (proxy_read_timeout), also D_Client > 3,33 Flüge/s.
- Jede inverse Serie (40 Schritte, alle 3 Verfahren): t_Client < 300 s.
- Aufwand <= 3 Aufrufe je Serie (Rakete, Serie, CSV),
  unabhängig von der Schrittzahl.

Begründung: Die Schwelle prüft die bisher ungemessenen Annahmen
1000 / 40 / 300 s. c_w beeinflusst den Durchsatz nicht; diese
Schwelle ist systembezogen.
Verfehlt (504 oder Zeit >= 300 s): unverändert berichten; Grenzen
begründet senken; erneut messen (Results-Methodik-Schleife).
Zu notieren: CPU, RAM, Windows-Build, Docker Desktop, WSL-2-Speicher
[VOM STUDENTEN EINTRAGEN]; während der Messung keine anderen
rechenintensiven Programme.

Voraussetzung für Abschnitt 3 (aus denselben Serien, nur Ja/Nein):
Monotonie je Rakete. Geprüft wird: keine Abnahme zwischen Nachbarn;
streng steigend ab dem ersten Apogäum > 0. Verletzung -> Rakete aus
Abschnitt 3 nehmen und berichten.

## 3. KPI Algorithmenvergleich (Teilfrage 3, Entscheidung 97 C2+)

Gleiche Bedingungen: tol = 1 Pa, P_MIN 1 kPa, P_MAX 1000 kPa,
step0 = 50 kPa (Annahme, wird NICHT nachträglich verändert).
Je Rakete und Verfahren (binary, exponential, interpolation mit
Illinois) eine inverse Serie mit 40 Zielhöhen, linear von 5 % bis
95 % von h(P_MAX). h(P_MAX) wird vom Skript aus der letzten Zeile der
Vorwärtsserie gelesen, ohne Ausgabe.

Kennzahlen je Suche: search_evaluations (Flüge der Suche;
hardwareunabhängig, vgl. Übungsfrage Skript S. 109 "Anzahl der
Vergleiche"); Treffgenauigkeit delta = |apogee - target_apogee| /
target_apogee (aus dem CSV).

Pflicht-KPIs:
- K1: alle 30 Serien ohne 422, also 100 % konvergiert.
- K2: delta <= S/100 für jede Suche (Begründung wie Abschnitt 1).

Vorhersagen (vor der Messung festgelegt, Ergebnis unverändert):
- H1: binär = 22 Auswertungen bei jeder Suche.
- H2: exponentiell nach Lage des gefundenen p* (Überdruck):
  bis 51 kPa: 18; bis 101 kPa: 19; bis 201 kPa: 21;
  bis 401 kPa: 23; darüber: 25.
  Suchen mit p* weniger als 1 Pa von einer Grenze entfernt werden
  getrennt berichtet. Folge: Im Bereich über 2,01 bar ist die
  Exponentialsuche teurer als die binäre.
- H3: Interpolation mit Illinois braucht je Rakete im Median weniger
  als 22 Auswertungen. Begründung: Dowell & Jarratt 1971, S. 170,
  Effizienzindex 3^(1/3) = 1,442 gegenüber 1 für die einfache Regula
  falsi; der Vergleich mit der Halbierung ist eigene Einordnung.

Wirkung der Ereignissuche (direkter Physikaufruf, nicht über die API):
- Nachbau von simulate_flight mit searcher-Parameter im
  Experiment-Ordner. Vor jeder Nutzung Ja/Nein-Prüfung: mit
  BinarySearch bitgleich zu simulate_flight.
- Variante "Schrittende": Das Ereignis liegt am Ende des RK4-Schritts,
  in dem es eintritt (wie die erste Version ohne Suche).
- Delta_E = (h_Schrittende - h_Suche) / h_Suche je Rakete,
  c_w = 0,345, Nennkonfiguration.
- Klassifikation vorab: |Delta_E| >= S/100 -> "wirksam", sonst
  "für das Apogäum vernachlässigbar". Beide Ausgänge werden berichtet.
- Beschreibend, kein KPI: Auswertungen der Ereignissuche für
  BinarySearch und InterpolationSearch. Die Exponentialsuche ist hier
  nicht anwendbar, weil sie nur steigende Funktionen sucht.
- Luftstoß-Ende ohne Suche bleibt Limitation.

Nicht Teil der Messung (Future Work): Interpolation ohne Illinois und
deren Abbruchgrund.

## 4. Regeln

- Skripte geben nur Ja/Nein und Dateinamen aus, keine Messwerte.
- Rohdaten unverändert ins Repo (CRLF wie bisher), dann Auswertung
  mit Tests, erst danach Werte ansehen.
- Verfehlte KPIs und widerlegte Vorhersagen werden unverändert
  berichtet und in der Discussion erklärt.
- Änderungen an dieser Notiz nur als datierter Nachtrag.

## 5. Reihenfolge

1. Durchsatz vorwärts + Monotonie (Abschnitt 2); liefert h(P_MAX).
2. Algorithmenvergleich invers (Abschnitt 3, K1 bis H3); liefert die
   inversen Zeiten für Abschnitt 2.
3. Analytische Lösung F1/F2 (Abschnitt 1) und Wirkung der
   Ereignissuche.
4. Parameterstudie mit eigener Vorab-Notiz, einschließlich KPI
   "Konfigurationsbandbreite" (Teilfrage 2).