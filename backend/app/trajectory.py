"""Flugkurve für die Anzeige ausdünnen.

Die Simulation liefert jeden Integrationsschritt als Punkt (t, h, v). In
den Schubphasen ist der Zeitschritt 100-mal feiner als im Freiflug, daher
liegt dort der größte Teil der Punkte, obwohl die Phasen nur einen kleinen
Teil der Flugzeit ausmachen. Für ein Diagramm reichen einige hundert
Punkte.

Verfahren (zeitliches Raster): Ein Punkt wird behalten, wenn seit dem
zuletzt behaltenen Punkt mindestens (t_Ende - t_Start) / (max_points - 1)
vergangen ist. Erster und letzter Punkt bleiben immer erhalten; der letzte
Punkt ist das Apogäum und bleibt damit exakt. Es werden nur vorhandene
Punkte ausgewählt, nichts wird interpoliert.

Ergebnis: höchstens max_points Punkte in der ursprünglichen Reihenfolge.
Zwischen zwei behaltenen Punkten liegt höchstens ein Rasterschritt plus der
größte Zeitschritt der Simulation.

Dieses Modul gehört nicht zur Flugphysik: Es ändert keine Ergebnisse,
sondern nur, wie viele Punkte der Kurve angezeigt werden.
"""

Point = tuple[float, float, float]  # (t, h, v)

# Höchstzahl der Punkte einer angezeigten Flugkurve. Annahme: Ein Diagramm
# ist einige hundert Pixel breit, mehr Punkte sind nicht unterscheidbar.
MAX_POINTS = 500


def thin_trajectory(trajectory: list[Point], max_points: int = MAX_POINTS) -> list[Point]:
    """Wählt höchstens max_points Punkte auf einem zeitlichen Raster aus."""
    if max_points < 2:
        raise ValueError("max_points muss mindestens 2 sein")
    if len(trajectory) <= max_points:
        return list(trajectory)

    first, last = trajectory[0], trajectory[-1]
    if last[0] <= first[0]:
        raise ValueError("Die Zeit muss vom ersten zum letzten Punkt steigen")
    step = (last[0] - first[0]) / (max_points - 1)
    kept = [first]
    for point in trajectory[1:-1]:
        # Obergrenze ausdrücklich: Bei steigender Zeit ändert sie das
        # Ergebnis nicht, schützt aber vor Rundungsfehlern im Raster.
        if len(kept) == max_points - 1:
            break
        if point[0] - kept[-1][0] >= step:
            kept.append(point)
    kept.append(last)
    return kept