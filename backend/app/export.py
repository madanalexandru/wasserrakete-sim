"""CSV-Export gespeicherter Flüge.

Eine Zeile pro Flug, Spalten = Felder von FlightRead in derselben
Reihenfolge. So hat die CSV genau die Spalten und Werte der JSON-Antwort
eines einzelnen Flugs, und eine Änderung an FlightRead ändert beide.

Format:
- Komma als Trennzeichen, Punkt als Dezimalzeichen, Zeilenende CRLF,
  Anführungszeichen nur bei Bedarf (Standard des csv-Moduls).
- Kopfzeile = Feldnamen, ohne Einheiten (alle Werte in SI-Einheiten).
- Zahlen in voller Genauigkeit: str(float) ist die kürzeste Darstellung,
  die beim Einlesen exakt denselben Wert ergibt.
- null -> leeres Feld; created_at im ISO-8601-Format wie in der JSON-Antwort.
- Der Inhalt ist reines ASCII; ein Byte-Order-Mark ist daher nicht nötig.

Die Funktion sortiert nicht: Die Zeilen erscheinen in der übergebenen
Reihenfolge. Die Reihenfolge legt die Abfrage fest.
"""

import csv
import io
from collections.abc import Iterable

from app.schemas import FlightRead

# Spaltenreihenfolge der CSV = Feldreihenfolge von FlightRead
CSV_COLUMNS = tuple(FlightRead.model_fields)


def flights_to_csv(flights: Iterable) -> str:
    """Flüge (Zeilen der Tabelle flights) -> CSV-Text mit Kopfzeile."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for flight in flights:
        # Derselbe Weg wie die JSON-Antwort: Werte über FlightRead lesen
        row = FlightRead.model_validate(flight).model_dump(mode="json")
        writer.writerow(row[name] for name in CSV_COLUMNS)  # None -> ""
    return buffer.getvalue()