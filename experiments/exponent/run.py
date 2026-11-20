"""Wirkung des Expansionsexponenten: Apogäum je Rakete und β direkt in der Physik.

Vorab-Notiz: docs/validation/exponent_plan.md

Rechnet R0-R9 (wie tool_vergleich) und E1-E4 (wie stichprobe) mit c_w' für
β = 1,4 (Kontrolle, ohne jede Änderung) und β = 1,17; 1,20; 1,22. Nur zur
Laufzeit und nur in der Wasserphase werden geändert:
    - waterphase.GAMMA (Druck p = p0 · (V_L,0 / V_L)^β),
    - simulation.temperature_after_expansion (Temperatur am Ende der
      Wasserphase, polytrop mit β).
Der Luftstoß bleibt bei γ = 1,4. Der Code in backend/app bleibt unverändert.

Die Kontrolle (β = 1,4 bitgleich mit h_modell aus vergleich.csv und
stichprobe.csv) muss bestehen, sonst wird nichts geschrieben.
Geschrieben wird data/werte.csv (volle Genauigkeit). Auf der Konsole
erscheinen bewusst keine Ergebniswerte.

Start (PowerShell, im Repo-Ordner; Wegwerf-Container, backend nur lesend):
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\\backend:/backend:ro" -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python exponent/run.py
"""

import contextlib
import csv
import importlib.util
import sys
from pathlib import Path

from app.physics import simulation, waterphase
from app.physics.simulation import MODEL_VERSION, RocketConfig

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_DIR = HERE / "data"
VALUES_NAME = "werte.csv"
CONTROL_BETA = 1.4
BETAS = [1.17, 1.20, 1.22]
REFERENCES = [
    ROOT / "tool_vergleich" / "results" / "vergleich.csv",
    ROOT / "stichprobe" / "results" / "stichprobe.csv",
]


def load_run(folder):
    """Lädt <folder>/run.py unter eigenem Namen (nur Konstanten und Funktionen)."""
    spec = importlib.util.spec_from_file_location(f"run_{folder}", ROOT / folder / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rockets():
    """Liste (Kürzel, Konfiguration): R0-R9 wie tool_vergleich, E1-E4 wie stichprobe, je mit c_w'."""
    tv, sp = load_run("tool_vergleich"), load_run("stichprobe")
    out = [(label, dict(config)) for label, config in tv.rockets()]
    out += [(label, {**config, "c_w": sp.CW_STRICH}) for label, config in sp.corners()]
    return out


def references():
    """Kürzel -> h_modell (float) aus den fertigen Ergebnissen."""
    ref = {}
    for path in REFERENCES:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ref[r["label"]] = float(r["h_modell_m"])
    return ref


def polytropic_temperature(beta):
    """Temperatur am Ende der Wasserphase bei polytroper Expansion mit β."""
    def temperature(t0, p, p0):
        return t0 * (p / p0) ** ((beta - 1) / beta)
    return temperature


@contextlib.contextmanager
def exponent(beta):
    """Setzt β nur zur Laufzeit in der Wasserphase und stellt danach alles wieder her."""
    old_gamma = waterphase.GAMMA
    old_temperature = simulation.temperature_after_expansion
    waterphase.GAMMA = beta
    simulation.temperature_after_expansion = polytropic_temperature(beta)
    try:
        yield
    finally:
        waterphase.GAMMA = old_gamma
        simulation.temperature_after_expansion = old_temperature


def apogee(config, beta):
    """Apogäum; bei β = 1,4 ohne jede Änderung (Kontrolle)."""
    cfg = RocketConfig(**config)
    if beta == CONTROL_BETA:
        return simulation.simulate_flight(cfg).apogee
    with exponent(beta):
        return simulation.simulate_flight(cfg).apogee


def measure():
    if MODEL_VERSION != "1":
        raise RuntimeError(f"MODEL_VERSION {MODEL_VERSION} statt 1 (Plan)")
    ref = references()
    rows, mismatched = [], []
    for label, config in rockets():
        h_control = apogee(config, CONTROL_BETA)
        if h_control != ref[label]:
            mismatched.append(label)
        rows.append({"label": label, "beta": CONTROL_BETA, "apogee": h_control})
        for beta in BETAS:
            rows.append({"label": label, "beta": beta, "apogee": apogee(config, beta)})
        print(f"{label}: gerechnet")
    if waterphase.GAMMA != CONTROL_BETA:
        raise RuntimeError("GAMMA wurde nicht wiederhergestellt")
    if mismatched:
        raise RuntimeError(f"Kontrolle nicht bitgleich bei: {', '.join(mismatched)}")
    print("Kontrolle bitgleich: ja")
    return rows


def write_values(rows, data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / VALUES_NAME, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["label", "beta", "apogee_m"])
        for r in rows:
            w.writerow([r["label"], repr(r["beta"]), repr(r["apogee"])])


def main(data_dir=DATA_DIR):
    if (data_dir / VALUES_NAME).exists():
        print(f"Abbruch: {data_dir / VALUES_NAME} existiert bereits (schon gemessen).")
        return 2
    try:
        rows = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben.")
        return 1
    write_values(rows, data_dir)
    print(f"Fertig: {len(rows)} Flüge in {data_dir / VALUES_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())