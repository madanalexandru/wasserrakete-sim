# Wasserraketen-Simulation

Containerisiertes Fullstack-Tool, das den senkrechten Flug einer
Wasserrakete simuliert (Wasserschub, Luftstoß, Freiflug) und das
Apogäum berechnet. Es speichert Raketen, Flüge und Experimentserien in
PostgreSQL, sucht im inversen Modus den Startdruck für eine Zielhöhe und
exportiert Serien als CSV.

Projektbericht „Ein Fullstack-Simulationstool für Wasserraketen“ (Nachprüfung 2026) zur Vorlesung „Full Stack Handwerk“, DHBW Ravensburg.
Modell, Annahmen, Messungen und Grenzen stehen im Projektbericht; dieses
README beschreibt nur die Bedienung.

## Schnellstart

Voraussetzung: Docker Desktop läuft. Getestet unter Windows mit Docker
Desktop (WSL 2) in PowerShell.

```powershell
git clone https://github.com/madanalexandru/wasserrakete-sim.git
cd wasserrakete-sim
docker compose up --build
```

Danach im Browser: <http://localhost>

Beenden: `Strg+C`, dann `docker compose down`. Die Daten bleiben im
Docker-Volume erhalten. `docker compose down -v` löscht sie.

Alle Befehle in diesem README gelten für PowerShell im Hauptordner des
Repos. In Bash sind sie gleich, außer wo ein Hinweis steht.

## Zugangsdaten und `.env`

Ohne `.env` gelten die Standardwerte aus `docker-compose.yml`. Das
Standard-Passwort ist kein Geheimnis: Es gilt nur lokal, und die
Datenbank hat keinen Port nach außen (nur das Frontend auf Port 80).

Eigene Werte:

```powershell
Copy-Item .env.example .env   # Bash: cp .env.example .env
```

Dann die Werte in `.env` ersetzen. `.env` wird nie committet.

- PostgreSQL übernimmt Benutzer und Passwort nur beim ersten Start mit
  leerem Volume. Nach einer Änderung startet die Datenbank erst wieder
  nach `docker compose down -v` (löscht alle Daten).
- `DEBUG=true` in `.env` schaltet die API-Dokumentation unter
  <http://localhost/api/docs> ein. Standard ist `false`.

## Aufbau

| Service    | Aufgabe                                                        |
|------------|----------------------------------------------------------------|
| `db`       | PostgreSQL 17, Daten im Volume `db-data`                       |
| `migrate`  | `alembic upgrade head`, beendet sich danach                    |
| `backend`  | FastAPI; startet erst nach erfolgreicher Migration             |
| `frontend` | Nginx: liefert `frontend/` aus, leitet `/api/` an das Backend  |
| `db-test`, `test` | nur Profil `test`: Testdatenbank im Arbeitsspeicher, Testlauf |
| `experiment` | nur Profil `experiment`: Messskripte, sprechen die API über Nginx an |

Alle Images sind per Digest fixiert, alle Python-Pakete per Sperrliste
(`backend/requirements*.txt`, `experiments/requirements.txt`).

## Bedienung im Browser

1. Rakete anlegen: Werte in den Einheiten des Formulars (l, bar, mm, g,
   °C). Komma oder Punkt als Dezimalzeichen.
2. Optional „Geometrie angeben“: Nasenkegel und Finnen. Dann zeigt das
   Tool Stabilitätswerte nach Barrowman (Druckpunkt, Schwerpunkte,
   Stabilitätsmaß in Kalibern), ohne Urteil.
3. „Flug simulieren“: Das Tool rechnet und speichert einen Flug und zeigt
   Apogäum und Flugkurve.

Ungültige Eingaben lehnt der Server mit HTTP 422 und einer Meldung ab,
z. B. wenn die Düse nicht kleiner als der Rumpf ist.

## API

Alle Werte in SI-Einheiten (m, m³, Pa, kg, K, s).

| Methode | Pfad                                   | Zweck                            |
|---------|----------------------------------------|----------------------------------|
| GET     | `/api/health`                          | Lebenszeichen                    |
| POST    | `/api/rockets`                         | Rakete anlegen                   |
| GET     | `/api/rockets/{id}`                    | Rakete mit Stabilitätswerten     |
| POST    | `/api/rockets/{id}/flights`            | Flug simulieren und speichern    |
| GET     | `/api/flights/{id}`                    | gespeicherter Flug               |
| GET     | `/api/flights/{id}/trajectory`         | Flugkurve (neu gerechnet)        |
| POST    | `/api/rockets/{id}/series`             | Experimentserie starten          |
| GET     | `/api/series/{id}`                     | Serie (Parameter, Rechenzeit)    |
| GET     | `/api/series/{id}/flights.csv`         | Serie als CSV                    |

Beispiel: Rakete anlegen, Startdruck von 1 bis 7 bar in 13 Schritten
variieren, CSV speichern (PowerShell):

```powershell
$api = "http://localhost/api"
$rakete = @{ name = "Beispiel"; v_bottle = 0.0015; v_water0 = 0.0005;
  p0_gauge = 500000; d_nozzle = 0.022; m_empty = 0.15; c_w = 0.5;
  d_body = 0.09 } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri "$api/rockets" -ContentType "application/json" -Body $rakete
$serie = @{ name = "Startdruck"; mode = "forward"; param_name = "p0_gauge";
  param_start = 100000; param_stop = 700000; n_steps = 13 } | ConvertTo-Json
$s = Invoke-RestMethod -Method Post -Uri "$api/rockets/$($r.id)/series" -ContentType "application/json" -Body $serie
Invoke-WebRequest -Uri "$api/series/$($s.id)/flights.csv" -OutFile serie.csv
```

Serien:

- `mode = "forward"`: `param_name` ist ein Pflichtfeld der Rakete
  (`v_bottle`, `v_water0`, `p0_gauge`, `d_nozzle`, `m_empty`, `c_w`,
  `d_body`, `temp0`); `n_steps` 2 bis 1000 Werte, gleichmäßig von
  `param_start` bis `param_stop`.
- `mode = "inverse"`: `param_name = "target_apogee"` (Zielhöhen in m,
  höchstens 40 Schritte). Das Tool sucht je Zielhöhe den Startdruck.
  `searcher`: `binary`, `exponential` (Standard) oder `interpolation`.
- Eine Serie läuft synchron. Nginx wartet höchstens 300 s auf die Antwort.

## CSV-Export

Eine Zeile pro Flug, Spalten in der Reihenfolge der JSON-Antwort eines
Flugs. Komma als Trennzeichen, Punkt als Dezimalzeichen, Zeilenende
CRLF, leere Felder für fehlende Werte. Alle Zahlen in SI-Einheiten und
voller Genauigkeit.

| Spalte | Einheit | Bedeutung |
|--------|---------|-----------|
| `id`, `rocket_id`, `series_id` | – | Flug, Rakete, Serie (leer = Einzelflug) |
| `created_at` | ISO 8601 | Zeitpunkt der Rechnung |
| `model_version` | – | Version von Physik und Suche |
| `v_bottle`, `v_water0` | m³ | Flaschenvolumen, Wasser beim Start |
| `p0_gauge` | Pa | Startdruck als Überdruck |
| `d_nozzle`, `d_body` | m | Düsen- und Rumpfdurchmesser |
| `m_empty` | kg | Leermasse |
| `c_w` | – | Luftwiderstandsbeiwert |
| `temp0` | K | Lufttemperatur beim Start |
| `nose_shape`, `n_fins` | – | `cone`/`ogive`; 3 oder 4 Finnen |
| `l_nose`, `fin_root_chord`, `fin_tip_chord`, `fin_span`, `fin_sweep`, `x_fin`, `x_cg_empty`, `l_total` | m | Geometrie; `x_fin` und `x_cg_empty` ab Nasenspitze |
| `target_apogee` | m | Zielhöhe (nur invers) |
| `searcher`, `search_evaluations` | – | Suchverfahren und Anzahl ihrer Auswertungen (nur invers) |
| `apogee` | m | Apogäum |
| `t_apogee`, `t_water_end`, `t_air_end` | s | Zeitpunkt Apogäum, Ende Wasserschub, Ende Luftstoß |
| `v_burnout` | m/s | Geschwindigkeit am Ende des Schubs |
| `h_burnout` | m | Höhe am Ende des Schubs |
| `water_rest` | m³ | nicht ausgestoßenes Wasser |

## Tests

**Backend** (pytest; SQLite im Arbeitsspeicher und eine eigene
PostgreSQL-Testdatenbank):

```powershell
docker compose --profile test run --rm test
docker compose rm -sf db-test
```

Die Testdatenbank liegt nur im Arbeitsspeicher und ist von den echten
Daten getrennt. Die Integrationstests laufen nur gegen eine Datenbank,
deren Name auf `_test` endet.

**Frontend** (`frontend/lib.js`, eingebauter Testläufer von Node):

```powershell
docker run --rm -v "${PWD}:/repo:ro" -w /repo node:24.22.0-alpine@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f node --test "frontend-tests/*.test.js"
```

**Experiment-Skripte** (ohne laufenden Stack):

```powershell
docker compose --profile experiment run --rm --no-deps experiment sh -c 'pip install -q --root-user-action=ignore -r requirements.txt && for d in analytisch cw_sensitivitaet tool_vergleich parameterstudie durchsatz algorithmen uebersicht stichprobe; do python -W error -m unittest discover -s $d || exit 1; done'
```

Die Ereignissuche rechnet direkt in der Physik und braucht dafür
`backend/` (Bash: `$PWD/backend` statt `${PWD}\backend`):

```powershell
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\backend:/backend:ro" -v "${PWD}\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python -W error -m unittest discover -s ereignissuche -v
```

## Experimente und Abbildungen

Jeder Ordner in `experiments/` enthält `run.py` (misst über die API und
speichert Rohdaten in `data/`), `evaluate.py` (wertet aus und schreibt
nach `results/`) und Tests. Die Messpläne mit KPIs stehen in
`docs/validation/` (Vorab-Notizen mit datierten Nachträgen).

| Ordner | Inhalt | Abbildung in `results/` |
|--------|--------|-------------------------|
| `analytisch` | Vergleich mit der analytischen Lösung ohne Luftwiderstand | – |
| `cw_sensitivitaet` | Einfluss von c_w auf das Apogäum | `abbildung_cw` |
| `tool_vergleich` | Vergleich mit dem Referenztool | `abbildung_vergleich` |
| `parameterstudie` | Füllstand-Serien über ein Raster von Raketen | `abbildung_fuellstand` |
| `durchsatz` | große Vorwärtsserien, Zeiten, Monotonie | – |
| `algorithmen` | inverse Serien je Suchverfahren | `abbildung_suchaufwand` |
| `ereignissuche` | Wirkung der Ereignissuche (direkt in der Physik) | – |
| `stichprobe` | Vier Eckraketen gegen das Referenztool, Ursachenprüfung je Flugphase | `abbildung_stichprobe` |
| `uebersicht` | Übersicht System und Experiment-Workflow | `abbildung_uebersicht` |

Abbildungen jeweils als PNG und SVG.

**Ergebnisse und Abbildungen aus den committeten Rohdaten neu erzeugen:**

```powershell
docker compose --profile experiment run --rm --no-deps experiment sh -c 'pip install -q --root-user-action=ignore -r requirements.txt && for d in analytisch cw_sensitivitaet tool_vergleich parameterstudie durchsatz algorithmen stichprobe; do python $d/evaluate.py || exit 1; done && python stichprobe/ursache.py && python uebersicht/zeichne.py'
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python ereignissuche/evaluate.py
git status
```

Erwartet: `git status` zeigt keine geänderten Dateien. Die neu erzeugten
Dateien sind also bytegleich mit den committeten.

Ausnahme: PNG-Dateien können als geändert erscheinen, obwohl jedes Pixel
gleich ist. Beobachtet in einer Linux-Testumgebung auf einem anderen
Prozessor: Nur die komprimierten Bilddaten unterschieden sich. CSV, MD
und SVG waren dort bytegleich und sind deshalb die Referenz.

**Neu messen:** z. B.

```powershell
docker compose --profile experiment run --rm experiment python cw_sensitivitaet/run.py
```

`run.py` bricht ab, wenn in `data/` schon Rohdaten liegen. So bleiben die
committeten Messungen geschützt. Für eine neue Messung den Ordner
`data/` vorher umbenennen. `algorithmen/run.py` liest Zielhöhen aus den
Rohdaten von `durchsatz`. Für die Ereignissuche den `docker run`-Befehl
aus „Tests“ verwenden, mit `python ereignissuche/run.py` am Ende.

## Ordnerstruktur

```text
backend/          FastAPI-App, Physik (app/physics), Suche (app/search),
                  Alembic-Migrationen, Tests
frontend/         Startseite, app.js, lib.js (von Nginx ausgeliefert)
frontend-tests/   Node-Tests für lib.js
nginx/            Nginx-Konfiguration
experiments/      Messskripte, Rohdaten, Ergebnisse, Abbildungen
docs/validation/  Messpläne, Funktionstest des Referenztools und Flaschenmessung
```

## Typische Probleme

- `failed to connect to the docker API`: Docker Desktop ist nicht
  gestartet.
- Port 80 ist belegt: anderen Webserver oder Container beenden, dann neu
  starten.
- Datenbank startet nach einer Änderung an `.env` nicht: siehe
  „Zugangsdaten und `.env`“ (Volume).
- `/api/docs` antwortet 404: `DEBUG` ist nicht `true`.
- `OSError: [Errno 22] Invalid argument` beim Schreiben einer Abbildung
  (Windows): Die Datei ist in einem anderen Programm geöffnet, z. B. in
  einem Bildbetrachter. Fenster schließen, Befehl wiederholen.