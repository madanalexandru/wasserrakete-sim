"""Wirkung der Ereignissuche: Varianten V0 bis V4 je Rakete direkt in der Physik rechnen.

Vorab-Notiz: docs/validation/kpi_uebrige_plan.md (Abschnitt 3, Nachtrag 5)

Nachbau von simulate_flight (MODEL_VERSION "1"), der je Phase ein eigenes
Suchverfahren an Wasserphase und Freiflug weitergibt und die Suchergebnisse
mitschreibt. Der Code in backend/app bleibt unverändert.

    V0  binär in beiden Phasen (muss bitgleich zu simulate_flight sein)
    V1  Interpolation (Illinois) in beiden Phasen
    V2  Schrittende in beiden Phasen (keine Suche)
    V3  nur Wasser-Ende am Schrittende, Freiflug binär
    V4  nur Apogäum am Schrittende, Wasserphase binär

"Schrittende" ist das Ersatz-Suchverfahren StepEnd: Es erfüllt Searchable
und liefert immer x = hi (= dt) ohne Auswertung. Damit ändert sich nur der
Zeitpunkt des Ereignisses; der übrige Code ist identisch.

Geschrieben wird data/werte.csv (Rohwerte in voller Genauigkeit). Auf der
Konsole erscheinen bewusst keine Ergebniswerte, nur Ja/Nein der
Bitgleich-Prüfung.

Start (PowerShell, im Repo-Ordner; Wegwerf-Container, backend nur lesend):
    docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/backend -v "${PWD}\\backend:/backend:ro" -v "${PWD}\\experiments:/experiments" -w /experiments python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 python ereignissuche/run.py
"""

import csv
import dataclasses
import sys
from pathlib import Path

from app.physics.airphase import simulate_airphase, temperature_after_expansion
from app.physics.freeflight import drag_factor, simulate_freeflight
from app.physics.simulation import (
    MODEL_VERSION, FlightResult, RocketConfig, simulate_flight,
)
from app.physics.waterphase import P_ATM, RHO_WATER, simulate_waterphase
from app.search.binary_search import BinarySearch
from app.search.interpolation_search import InterpolationSearch
from app.search.searchable import Searchable, SearchResult

DATA_DIR = Path(__file__).resolve().parent / "data"
VALUES_NAME = "werte.csv"
NACHBAU_VERSION = "1"  # Stand von simulate_flight, der hier nachgebaut ist

# Basisrakete in SI-Einheiten wie durchsatz/run.py: plausible Werte, NICHT gemessen.
BASE = {
    "v_bottle": 1.5e-3,
    "v_water0": 0.5e-3,
    "p0_gauge": 5e5,
    "d_nozzle": 0.022,
    "m_empty": 0.15,
    "c_w": 0.345,
    "d_body": 0.09,
}

# Varianten wie im Validierungssatz. R8/R9: Durchmesser als Anhaltswert,
# NICHT gemessen.
CHANGES = {
    "R0": {},
    "R1": {"p0_gauge": 3e5},
    "R2": {"p0_gauge": 7e5},
    "R3": {"v_water0": 0.3e-3},
    "R4": {"v_water0": 0.7e-3},
    "R5": {"d_nozzle": 0.015},
    "R6": {"m_empty": 0.10},
    "R7": {"m_empty": 0.25},
    "R8": {"v_bottle": 1.0e-3, "d_body": 0.079},
    "R9": {"v_bottle": 2.0e-3, "d_body": 0.102},
}


class StepEnd(Searchable):
    """Keine Suche: Das Ereignis liegt am Ende des RK4-Schritts (x = hi).

    f wird nicht aufgerufen (0 Auswertungen). converged = False, weil nichts
    gesucht wurde.
    """

    def search(self, f, target, lo, hi, tol):
        if not lo < hi:
            raise ValueError("Es muss gelten: lo < hi.")
        return SearchResult(hi, 0, 0, hi - lo, False)


class Recorder(Searchable):
    """Reicht die Suche an ein Verfahren weiter und merkt sich jedes Ergebnis."""

    def __init__(self, inner):
        self.inner = inner
        self.results = []

    def search(self, f, target, lo, hi, tol):
        result = self.inner.search(f, target, lo, hi, tol)
        self.results.append(result)
        return result


# Variante -> (Name, Verfahren Wasserphase, Verfahren Freiflug)
VARIANTS = {
    "V0": ("binaer", BinarySearch, BinarySearch),
    "V1": ("interpolation", InterpolationSearch, InterpolationSearch),
    "V2": ("schrittende", StepEnd, StepEnd),
    "V3": ("schrittende_wasser", StepEnd, BinarySearch),
    "V4": ("schrittende_apogaeum", BinarySearch, StepEnd),
}

COLUMNS = [
    "label", "variante", "name", "wasser", "freiflug", "apogee", "t_apogee",
    "t_water_end", "t_air_end", "h_burnout", "v_burnout", "water_rest",
    "wasser_auswertungen", "wasser_konvergiert", "freiflug_auswertungen",
    "freiflug_konvergiert", "bitgleich",
]


def rockets():
    """Liste (Kürzel, Konfiguration) in fester Reihenfolge R0 bis R9."""
    return [(label, {**BASE, **change}) for label, change in CHANGES.items()]


def flight(cfg, water_searcher, free_searcher):
    """Nachbau von simulate_flight mit einem Suchverfahren je Phase.

    Liefert (FlightResult, Suchergebnisse Wasserphase, Suchergebnisse Freiflug).
    """
    water_rec, free_rec = Recorder(water_searcher), Recorder(free_searcher)
    k = drag_factor(cfg.c_w, cfg.d_body)
    p0_abs = cfg.p0_gauge + P_ATM

    water = simulate_waterphase(
        cfg.v_bottle, cfg.v_water0, cfg.p0_gauge, cfg.d_nozzle, cfg.m_empty, k,
        searcher=water_rec,
    )
    temp = temperature_after_expansion(cfg.temp0, water.p_end, p0_abs)
    air = simulate_airphase(
        water.p_end, temp, cfg.v_bottle, cfg.d_nozzle, cfg.m_empty, k,
        h0=water.h_end, v0=water.v_end, t0=water.t_end,
    )
    trajectory = [(t, h, v) for t, h, v, _ in water.trajectory]
    trajectory += [(t, h, v) for t, h, v, _ in air.trajectory[1:]]

    m_free = cfg.m_empty + RHO_WATER * water.water_rest
    if air.v_end > 0:
        free = simulate_freeflight(
            air.h_end, air.v_end, m_free, k, t0=air.t_end, searcher=free_rec,
        )
        trajectory += free.trajectory[1:]
        apogee, t_apogee = free.apogee, free.t_apogee
    else:  # Rakete steigt nach dem Schub nicht mehr
        apogee, t_apogee = air.h_end, air.t_end

    result = FlightResult(
        apogee, t_apogee, water.t_end, air.t_end,
        air.v_end, air.h_end, water.water_rest, trajectory,
    )
    return result, water_rec.results, free_rec.results


def search_cells(results, searcher_cls, where):
    """(Auswertungen, konvergiert) einer Phase als Text."""
    if not results:
        return 0, "kein Freiflug"
    if len(results) != 1:
        raise RuntimeError(f"{where}: {len(results)} Suchen statt 1")
    if searcher_cls is StepEnd:
        return 0, "keine Suche"
    return results[0].evaluations, "ja" if results[0].converged else "nein"


def run_variant(label, cfg, variant):
    """Ein Flug in einer Variante. Liefert (Zeile, FlightResult)."""
    name, water_cls, free_cls = VARIANTS[variant]
    where = f"{label} {variant}"
    res, water_results, free_results = flight(cfg, water_cls(), free_cls())
    if not water_results:
        raise RuntimeError(f"{where}: Wasserphase ohne Suche")
    w_evals, w_conv = search_cells(water_results, water_cls, f"{where} Wasser")
    f_evals, f_conv = search_cells(free_results, free_cls, f"{where} Freiflug")
    row = {
        "label": label, "variante": variant, "name": name,
        "wasser": water_cls.__name__, "freiflug": free_cls.__name__,
        "apogee": repr(res.apogee), "t_apogee": repr(res.t_apogee),
        "t_water_end": repr(res.t_water_end), "t_air_end": repr(res.t_air_end),
        "h_burnout": repr(res.h_burnout), "v_burnout": repr(res.v_burnout),
        "water_rest": repr(res.water_rest),
        "wasser_auswertungen": w_evals, "wasser_konvergiert": w_conv,
        "freiflug_auswertungen": f_evals, "freiflug_konvergiert": f_conv,
        "bitgleich": "",
    }
    return row, res


def measure():
    """Alle Raketen und Varianten. Liefert (Zeilen, Anzahl nicht bitgleich)."""
    rows, not_equal = [], 0
    for label, config in rockets():
        cfg = RocketConfig(**config)
        reference = simulate_flight(cfg)
        for variant in VARIANTS:
            row, res = run_variant(label, cfg, variant)
            if variant == "V0":
                equal = dataclasses.asdict(res) == dataclasses.asdict(reference)
                row["bitgleich"] = "ja" if equal else "nein"
                not_equal += not equal
                print(f"{label}: V0 bitgleich zu simulate_flight: {'Ja' if equal else 'Nein'}")
            rows.append(row)
    return rows, not_equal


def write_values(rows, data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_dir / VALUES_NAME, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(data_dir=DATA_DIR):
    if (data_dir / VALUES_NAME).exists():
        print(f"Abbruch: {data_dir / VALUES_NAME} existiert bereits (schon gemessen).")
        return 2
    if MODEL_VERSION != NACHBAU_VERSION:
        print(f"Abbruch: MODEL_VERSION ist nicht {NACHBAU_VERSION}; Nachbau prüfen.")
        return 1
    try:
        rows, not_equal = measure()
    except RuntimeError as err:
        print(f"Abbruch: {err}")
        print("Nichts geschrieben.")
        return 1
    write_values(rows, data_dir)
    print(f"Fertig: {len(rows)} Zeilen in {data_dir / VALUES_NAME}")
    if not_equal:
        print(f"Achtung: {not_equal} Rakete(n) nicht bitgleich (werden nicht ausgewertet).")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())