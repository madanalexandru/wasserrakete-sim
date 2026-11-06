// Tests für frontend/lib.js mit dem eingebauten Testläufer von Node.
// Keine Pakete nötig; Ausführung siehe README bzw. Testbefehl.

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ALL_FIELDS,
  GEOMETRY_FIELDS,
  REQUIRED_FIELDS,
  buildPayload,
  fieldLabel,
  formatApiErrors,
  formatClientErrors,
  formatNumber,
  formatStability,
  fromSI,
  parseNumber,
  shiftDecimal,
  toSI,
} from "../frontend/lib.js";

// Feldnamen und Reihenfolge von RocketCreate (backend/app/schemas.py) ohne name.
// Ändert sich das Schema, muss diese Liste und lib.js angepasst werden.
const ROCKET_CREATE_FIELDS = [
  "v_bottle", "v_water0", "p0_gauge", "d_nozzle", "m_empty", "c_w", "d_body", "temp0",
  "nose_shape", "l_nose", "n_fins", "fin_root_chord", "fin_tip_chord", "fin_span",
  "fin_sweep", "x_fin", "x_cg_empty", "l_total",
];

// Beispielrakete in Oberflächeneinheiten (frei gewählt, NICHT gemessen).
const EXAMPLE_FORM = {
  name: "Beispiel",
  v_bottle: "1,5",
  v_water0: "0,5",
  p0_gauge: "5",
  d_nozzle: "22",
  m_empty: "150",
  c_w: "0,5",
  d_body: "90",
  temp0: "",
};

const GEOMETRY_FORM = {
  nose_shape: "ogive",
  l_nose: "120",
  n_fins: "3",
  fin_root_chord: "100",
  fin_tip_chord: "40",
  fin_span: "80",
  fin_sweep: "-10",
  x_fin: "300",
  x_cg_empty: "250",
  l_total: "400",
};

// --- Felder ---------------------------------------------------------------

test("Feldnamen und Reihenfolge wie RocketCreate", () => {
  assert.deepEqual(ALL_FIELDS.map((f) => f.api), ROCKET_CREATE_FIELDS);
});

test("Feldnamen sind eindeutig und haben Bezeichnung und gültige Art", () => {
  const names = ALL_FIELDS.map((f) => f.api);
  assert.equal(new Set(names).size, names.length);
  for (const f of ALL_FIELDS) {
    assert.ok(f.label.length > 0, f.api);
    assert.ok(f.kind === "number" || f.kind === "choice", f.api);
  }
});

test("Formular-Pflichtfelder: sieben, temp0 optional; Geometrie zehn Felder", () => {
  assert.equal(REQUIRED_FIELDS.length, 7);
  assert.ok(!REQUIRED_FIELDS.some((f) => f.api === "temp0"));
  assert.equal(GEOMETRY_FIELDS.length, 10);
});

// --- Zahlen einlesen ------------------------------------------------------

test("parseNumber akzeptiert Punkt, Komma, Exponent und Leerzeichen", () => {
  assert.equal(parseNumber("1,5"), 1.5);
  assert.equal(parseNumber("1.5"), 1.5);
  assert.equal(parseNumber(" 2 "), 2);
  assert.equal(parseNumber(".5"), 0.5);
  assert.equal(parseNumber("-10"), -10);
  assert.equal(parseNumber("1e3"), 1000);
  assert.equal(parseNumber("2,5E-1"), 0.25);
});

test("parseNumber: leer -> null", () => {
  assert.equal(parseNumber(""), null);
  assert.equal(parseNumber("   "), null);
  assert.equal(parseNumber(undefined), null);
});

test("parseNumber: keine Zahl -> NaN", () => {
  for (const s of ["abc", "0x10", "1.2.3", "1,5,0", "Infinity", "NaN", "1e", "--1", "1 000"]) {
    assert.ok(Number.isNaN(parseNumber(s)), s);
  }
});

// --- Umrechnung -----------------------------------------------------------

test("toSI rechnet ohne Rundungsrest um", () => {
  assert.equal(toSI(1.5, "l"), 0.0015);
  assert.equal(toSI(0.5, "l"), 0.0005);
  assert.equal(toSI(5, "bar"), 500000);
  assert.equal(toSI(0.3, "bar"), 30000);
  assert.equal(toSI(22, "mm"), 0.022);
  assert.equal(toSI(150, "g"), 0.15);
  assert.equal(toSI(0.5, "one"), 0.5);
  assert.equal(toSI(-10, "mm"), -0.01);
});

test("toSI Temperatur: 20 °C und 21,7 °C ohne Rest", () => {
  assert.equal(toSI(20, "degC"), 293.15);
  // Naiv ergäbe 21.7 + 273.15 den Wert 294.84999999999997.
  assert.equal(toSI(21.7, "degC"), 294.85);
  assert.equal(toSI(-5, "degC"), 268.15);
});

test("Ergebnis entspricht der direkt eingelesenen Dezimalzahl", () => {
  const cases = [
    [1.1, "l", "1.1e-3"], [0.7, "bar", "0.7e5"], [33.3, "mm", "33.3e-3"],
    [0.1, "g", "0.1e-3"], [123.456, "mm", "123.456e-3"],
  ];
  for (const [x, unit, literal] of cases) {
    assert.equal(toSI(x, unit), Number(literal), `${x} ${unit}`);
  }
});

test("shiftDecimal mit Exponent in der Darstellung", () => {
  assert.equal(shiftDecimal(1e-7, -3), 1e-10);
  assert.equal(shiftDecimal(1e21, 5), 1e26);
  assert.equal(shiftDecimal(0, -3), 0);
});

test("fromSI ist die Umkehrung von toSI", () => {
  const cases = [[1.5, "l"], [5, "bar"], [22, "mm"], [150, "g"], [21.7, "degC"], [0.5, "one"]];
  for (const [x, unit] of cases) {
    assert.equal(fromSI(toSI(x, unit), unit), x, `${x} ${unit}`);
  }
});

// --- Anfrage bauen --------------------------------------------------------

test("Beispielrakete ergibt exakte SI-Werte, temp0 leer wird nicht gesendet", () => {
  const { payload, errors } = buildPayload(EXAMPLE_FORM, false);
  assert.deepEqual(errors, []);
  assert.deepEqual(payload, {
    name: "Beispiel",
    v_bottle: 0.0015,
    v_water0: 0.0005,
    p0_gauge: 500000,
    d_nozzle: 0.022,
    m_empty: 0.15,
    c_w: 0.5,
    d_body: 0.09,
  });
});

test("temp0 ausgefüllt wird in Kelvin gesendet", () => {
  const { payload } = buildPayload({ ...EXAMPLE_FORM, temp0: "21,7" }, false);
  assert.equal(payload.temp0, 294.85);
});

test("Name wird getrimmt; leerer Name ist ein Fehler", () => {
  assert.equal(buildPayload({ ...EXAMPLE_FORM, name: "  R1 " }, false).payload.name, "R1");
  const { payload, errors } = buildPayload({ ...EXAMPLE_FORM, name: "  " }, false);
  assert.ok(!("name" in payload));
  assert.deepEqual(errors, [{ field: "name", msg: "Pflichtfeld" }]);
});

test("Leeres Pflichtfeld und keine Zahl ergeben Fehler, Feld wird nicht gesendet", () => {
  const form = { ...EXAMPLE_FORM, v_bottle: "", d_nozzle: "abc" };
  const { payload, errors } = buildPayload(form, false);
  assert.deepEqual(errors, [
    { field: "v_bottle", msg: "Pflichtfeld" },
    { field: "d_nozzle", msg: "keine Zahl" },
  ]);
  assert.ok(!("v_bottle" in payload));
  assert.ok(!("d_nozzle" in payload));
});

test("Zahl, die nach der Umrechnung unendlich wird, ist ein Fehler", () => {
  const { payload, errors } = buildPayload({ ...EXAMPLE_FORM, p0_gauge: "1e308" }, false);
  assert.deepEqual(errors, [{ field: "p0_gauge", msg: "Zahl zu groß" }]);
  assert.ok(!("p0_gauge" in payload));
});

test("Fachliche Regeln prüft der Server, nicht das Frontend", () => {
  // Wasser größer als Flasche und Druck 0: beide werden gesendet.
  const form = { ...EXAMPLE_FORM, v_water0: "2", p0_gauge: "0" };
  const { payload, errors } = buildPayload(form, false);
  assert.deepEqual(errors, []);
  assert.equal(payload.v_water0, 0.002);
  assert.equal(payload.p0_gauge, 0);
});

test("Ohne Häkchen wird keine Geometrie gesendet, auch wenn ausgefüllt", () => {
  const { payload, errors } = buildPayload({ ...EXAMPLE_FORM, ...GEOMETRY_FORM }, false);
  assert.deepEqual(errors, []);
  for (const f of GEOMETRY_FIELDS) assert.ok(!(f.api in payload), f.api);
});

test("Mit Häkchen wird die Geometrie in SI gesendet, Auswahl als Text bzw. Zahl", () => {
  const { payload, errors } = buildPayload({ ...EXAMPLE_FORM, ...GEOMETRY_FORM }, true);
  assert.deepEqual(errors, []);
  assert.equal(payload.nose_shape, "ogive");
  assert.equal(payload.n_fins, 3);
  assert.equal(payload.l_nose, 0.12);
  assert.equal(payload.fin_root_chord, 0.1);
  assert.equal(payload.fin_tip_chord, 0.04);
  assert.equal(payload.fin_span, 0.08);
  assert.equal(payload.fin_sweep, -0.01);
  assert.equal(payload.x_fin, 0.3);
  assert.equal(payload.x_cg_empty, 0.25);
  assert.equal(payload.l_total, 0.4);
});

test("Mit Häkchen: leere Geometriefelder werden weggelassen, kein Fehler im Frontend", () => {
  const form = { ...EXAMPLE_FORM, ...GEOMETRY_FORM, l_nose: "", n_fins: "" };
  const { payload, errors } = buildPayload(form, true);
  assert.deepEqual(errors, []);
  assert.ok(!("l_nose" in payload));
  assert.ok(!("n_fins" in payload));
  assert.equal(payload.fin_span, 0.08);
});

test("Ungültige Auswahl ist ein Fehler", () => {
  const form = { ...EXAMPLE_FORM, ...GEOMETRY_FORM, n_fins: "5", nose_shape: "kugel" };
  const { errors } = buildPayload(form, true);
  assert.deepEqual(errors, [
    { field: "nose_shape", msg: "ungültige Auswahl" },
    { field: "n_fins", msg: "ungültige Auswahl" },
  ]);
});

test("Anfrage enthält nie null, NaN oder unendlich", () => {
  const forms = [
    [EXAMPLE_FORM, false],
    [{ ...EXAMPLE_FORM, ...GEOMETRY_FORM }, true],
    [{ ...EXAMPLE_FORM, ...GEOMETRY_FORM, l_nose: "", d_nozzle: "x" }, true],
  ];
  for (const [form, geo] of forms) {
    const { payload } = buildPayload(form, geo);
    for (const [k, v] of Object.entries(payload)) {
      assert.ok(v !== null && v !== undefined, k);
      if (typeof v === "number") assert.ok(Number.isFinite(v), k);
    }
    // JSON-Rundreise verändert nichts.
    assert.deepEqual(JSON.parse(JSON.stringify(payload)), payload);
  }
});

// --- Fehleranzeige --------------------------------------------------------

test("422 von Pydantic: Feld mit deutscher Bezeichnung, Meldung unverändert", () => {
  const body = {
    detail: [
      { type: "greater_than", loc: ["body", "d_nozzle"], msg: "Input should be greater than 0", input: 0 },
      { type: "missing", loc: ["body", "v_bottle"], msg: "Field required" },
    ],
  };
  assert.deepEqual(formatApiErrors(422, body), [
    "Düsendurchmesser: Input should be greater than 0",
    "Flaschenvolumen: Field required",
  ]);
});

test("422 einer Kombinationsregel (loc nur body) erscheint als Eingabe", () => {
  const body = {
    detail: [{ type: "value_error", loc: ["body"], msg: "Value error, v_water0 muss kleiner als v_bottle sein" }],
  };
  assert.deepEqual(formatApiErrors(422, body), [
    "Eingabe: Value error, v_water0 muss kleiner als v_bottle sein",
  ]);
});

test("422 mit Pfad oder Schritt", () => {
  const body = {
    detail: [
      { loc: ["path", "rocket_id"], msg: "nicht rechenbar", type: "simulation_error" },
      { loc: ["body", "steps", 3], msg: "Schritt 3 …", type: "value_error" },
      { loc: ["query", "x"], msg: "m", type: "t" },
    ],
  };
  assert.deepEqual(formatApiErrors(422, body), [
    "Rakete: nicht rechenbar",
    "Schritt 3: Schritt 3 …",
    "query.x: m",
  ]);
});

test("Unbekanntes Feld im loc bleibt als Name stehen", () => {
  const body = { detail: [{ loc: ["body", "fin_sweeep"], msg: "Extra inputs are not permitted" }] };
  assert.deepEqual(formatApiErrors(422, body), ["fin_sweeep: Extra inputs are not permitted"]);
});

test("404 mit Text in detail", () => {
  assert.deepEqual(formatApiErrors(404, { detail: "Rakete nicht gefunden" }), ["Rakete nicht gefunden"]);
});

test("500 ohne JSON und unerwartete Antworten", () => {
  assert.deepEqual(formatApiErrors(500, null), ["Serverfehler (HTTP 500)"]);
  assert.deepEqual(formatApiErrors(502, { foo: 1 }), ["Serverfehler (HTTP 502)"]);
  assert.deepEqual(formatApiErrors(422, { detail: [] }), ["Unerwartete Antwort (HTTP 422)"]);
  assert.deepEqual(formatApiErrors(400, "text"), ["Unerwartete Antwort (HTTP 400)"]);
});

test("Eintrag ohne loc oder msg bricht nicht ab", () => {
  assert.deepEqual(formatApiErrors(422, { detail: [{}, null] }), [
    "Eingabe: unbekannter Fehler",
    "Eingabe: unbekannter Fehler",
  ]);
});

test("Fehler des Frontends im selben Zeilenformat", () => {
  assert.deepEqual(
    formatClientErrors([{ field: "name", msg: "Pflichtfeld" }, { field: "c_w", msg: "keine Zahl" }]),
    ["Name: Pflichtfeld", "Luftwiderstandsbeiwert c_w: keine Zahl"],
  );
  assert.equal(fieldLabel("unbekannt"), "unbekannt");
});

// --- Stabilitätswerte -----------------------------------------------------

test("Ohne Geometrie keine Stabilitätszeilen", () => {
  assert.deepEqual(formatStability(null), []);
  assert.deepEqual(formatStability(undefined), []);
});

test("Stabilitätswerte in mm und Kalibern mit Komma", () => {
  const rows = formatStability({
    x_cp: 0.31234, x_cg_start: 0.4, x_cg_empty: 0.25, margin_start: -0.966, margin_empty: 0.5678,
  });
  assert.deepEqual(rows.map((r) => r.text), [
    "312,3 mm", "400,0 mm", "250,0 mm", "-0,97 Kaliber", "0,57 Kaliber",
  ]);
  assert.equal(rows.length, 5);
});

test("Stabilitätswerte ohne Bewertung", () => {
  const rows = formatStability({ x_cp: 0.3, x_cg_start: 0.4, x_cg_empty: 0.2, margin_start: -1, margin_empty: 1 });
  const all = rows.map((r) => `${r.label} ${r.text}`).join(" ").toLowerCase();
  for (const word of ["instabil", "stabil ", "gut", "schlecht", "warnung", "gefahr"]) {
    assert.ok(!all.includes(word), word);
  }
});

test("formatNumber rundet nur die Anzeige", () => {
  assert.equal(formatNumber(1.25, 1), "1,3");
  assert.equal(formatNumber(2, 2), "2,00");
});