// Reine Hilfsfunktionen des Frontends, ohne Zugriff auf die Seite.
// Dadurch lassen sie sich mit dem Testläufer von Node prüfen.
// Inhalt: Formular (Feldlisten, Umrechnung, Anfrage, Fehler, Stabilität)
// und Flugkurve (Zeichendaten für das Diagramm, Apogäum als Text).
//
// Die API rechnet in SI-Einheiten. Die Oberfläche nutzt feste, gewohnte
// Einheiten (l, bar, mm, g, °C) und rechnet vor dem Senden um.
// Alle fachlichen Regeln (Grenzen, Kombinationen, Geometrie alles oder
// nichts) prüft der Server; hier wird nur geprüft, ob ein Pflichtfeld
// ausgefüllt und jede Eingabe eine Zahl ist.

// Einheiten: Faktor als Zehnerpotenz (exp) oder Verschiebung (offset).
export const UNITS = {
  l: { label: "l", exp: -3 }, // Liter -> m³
  bar: { label: "bar", exp: 5 }, // bar -> Pa
  mm: { label: "mm", exp: -3 }, // mm -> m
  g: { label: "g", exp: -3 }, // g -> kg
  degC: { label: "°C", offset: 273.15 }, // °C -> K
  one: { label: "–", exp: 0 }, // ohne Einheit
};

// Felder in der Reihenfolge von RocketCreate (ohne name).
// kind: "number" (Zahl mit Einheit) oder "choice" (feste Auswahl).
export const REQUIRED_FIELDS = [
  { api: "v_bottle", label: "Flaschenvolumen", kind: "number", unit: "l" },
  { api: "v_water0", label: "Wasservolumen beim Start", kind: "number", unit: "l" },
  { api: "p0_gauge", label: "Startdruck (Überdruck)", kind: "number", unit: "bar" },
  { api: "d_nozzle", label: "Düsendurchmesser", kind: "number", unit: "mm" },
  { api: "m_empty", label: "Leermasse", kind: "number", unit: "g" },
  { api: "c_w", label: "Luftwiderstandsbeiwert c_w", kind: "number", unit: "one" },
  { api: "d_body", label: "Rumpfdurchmesser", kind: "number", unit: "mm" },
];

// Optional: leer lassen -> Standardwert des Servers.
export const OPTIONAL_FIELDS = [
  { api: "temp0", label: "Lufttemperatur beim Start", kind: "number", unit: "degC" },
];

// Geometrie nach Barrowman: Längen ab Nasenspitze.
export const GEOMETRY_FIELDS = [
  { api: "nose_shape", label: "Nasenform", kind: "choice", choices: ["cone", "ogive"] },
  { api: "l_nose", label: "Länge Nasenkegel", kind: "number", unit: "mm" },
  { api: "n_fins", label: "Anzahl Finnen", kind: "choice", choices: [3, 4] },
  { api: "fin_root_chord", label: "Finnen-Wurzeltiefe c_r", kind: "number", unit: "mm" },
  { api: "fin_tip_chord", label: "Finnen-Spitzentiefe c_t", kind: "number", unit: "mm" },
  { api: "fin_span", label: "Finnen-Spannweite s", kind: "number", unit: "mm" },
  { api: "fin_sweep", label: "Finnen-Pfeilung x_t", kind: "number", unit: "mm" },
  { api: "x_fin", label: "Nasenspitze bis Finne", kind: "number", unit: "mm" },
  { api: "x_cg_empty", label: "Schwerpunkt leer (gemessen)", kind: "number", unit: "mm" },
  { api: "l_total", label: "Gesamtlänge", kind: "number", unit: "mm" },
];

export const ALL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS, ...GEOMETRY_FIELDS];

const LABELS = Object.fromEntries([
  ["name", "Name"],
  ...ALL_FIELDS.map((f) => [f.api, f.label]),
]);

// Dezimalzahl mit Punkt oder Komma, optional mit Exponent.
const NUMBER_PATTERN = /^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$/;

// Text -> Zahl. Leer -> null. Keine Zahl -> NaN.
export function parseNumber(text) {
  const s = String(text ?? "").trim();
  if (s === "") return null;
  if (!NUMBER_PATTERN.test(s)) return NaN;
  return Number(s.replace(",", "."));
}

// x · 10^exp ohne Rundungsrest der Multiplikation: Die kürzeste
// Dezimaldarstellung von x wird nur im Exponenten verschoben und neu
// eingelesen. Ergebnis ist die Gleitkommazahl, die der verschobenen
// Dezimalzahl am nächsten liegt (1,5 l -> 0.0015 statt 0.0015000000000000002).
export function shiftDecimal(x, exp) {
  const [mantissa, e = "0"] = String(x).split("e");
  return Number(`${mantissa}e${Number(e) + exp}`);
}

// Addition mit Rundung auf 10 Nachkommastellen, damit z. B.
// 21,7 °C -> 294.85 K ergibt statt 294.84999999999997.
// Eingaben mit mehr als 10 Nachkommastellen werden dabei gerundet.
function addDecimal(x, offset) {
  return Number((x + offset).toFixed(10));
}

// Wert in Oberflächeneinheit -> SI.
export function toSI(value, unitKey) {
  const unit = UNITS[unitKey];
  if (unit.offset !== undefined) return addDecimal(value, unit.offset);
  return shiftDecimal(value, unit.exp);
}

// SI -> Oberflächeneinheit (für die Anzeige).
export function fromSI(value, unitKey) {
  const unit = UNITS[unitKey];
  if (unit.offset !== undefined) return addDecimal(value, -unit.offset);
  return shiftDecimal(value, -unit.exp);
}

// Formularwerte (Texte) -> Anfrage für POST /api/rockets.
// form: { name, <api-Name>: Text, ... }, withGeometry: Häkchen gesetzt?
// Ergebnis: { payload, errors } mit errors als Liste { field, msg }.
// Leere optionale Felder werden nicht gesendet. Bei gesetztem Häkchen
// werden alle ausgefüllten Geometriefelder gesendet; ob die Geometrie
// vollständig ist, prüft der Server.
export function buildPayload(form, withGeometry) {
  const payload = {};
  const errors = [];

  const name = String(form.name ?? "").trim();
  if (name === "") errors.push({ field: "name", msg: "Pflichtfeld" });
  else payload.name = name;

  const fields = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS];
  if (withGeometry) fields.push(...GEOMETRY_FIELDS);
  const required = new Set(REQUIRED_FIELDS.map((f) => f.api));

  for (const f of fields) {
    const text = String(form[f.api] ?? "").trim();
    if (text === "") {
      if (required.has(f.api)) errors.push({ field: f.api, msg: "Pflichtfeld" });
      continue;
    }
    if (f.kind === "choice") {
      const choice = f.choices.find((c) => String(c) === text);
      if (choice === undefined) errors.push({ field: f.api, msg: "ungültige Auswahl" });
      else payload[f.api] = choice;
      continue;
    }
    const value = parseNumber(text);
    if (!Number.isFinite(value)) {
      errors.push({ field: f.api, msg: "keine Zahl" });
      continue;
    }
    // Nach der Umrechnung erneut prüfen: 1e308 bar wäre unendlich,
    // und JSON.stringify würde daraus still null machen.
    const si = toSI(value, f.unit);
    if (!Number.isFinite(si)) {
      errors.push({ field: f.api, msg: "Zahl zu groß" });
      continue;
    }
    payload[f.api] = si;
  }
  return { payload, errors };
}

// Feldname -> deutsche Bezeichnung; unbekannte Namen bleiben stehen.
export function fieldLabel(name) {
  return LABELS[name] ?? String(name);
}

// Ort eines API-Fehlers (loc) -> lesbare Bezeichnung.
function locLabel(loc) {
  if (!Array.isArray(loc) || loc.length === 0) return "Eingabe";
  if (loc[0] === "body" && loc.length === 1) return "Eingabe";
  if (loc[0] === "body" && loc[1] === "steps" && loc.length >= 3) return `Schritt ${loc[2]}`;
  if (loc[0] === "body") return fieldLabel(loc[1]);
  if (loc[0] === "path" && loc[1] === "rocket_id") return "Rakete";
  return loc.join(".");
}

// Antwort des Servers -> Zeilen für die Fehlerliste.
// status: HTTP-Status; body: gelesenes JSON oder null (kein JSON).
// Die Meldungen des Servers werden unverändert übernommen.
export function formatApiErrors(status, body) {
  const detail = body && typeof body === "object" ? body.detail : undefined;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((d) => `${locLabel(d?.loc)}: ${d?.msg ?? "unbekannter Fehler"}`);
  }
  if (typeof detail === "string" && detail !== "") return [detail];
  if (status >= 500) return [`Serverfehler (HTTP ${status})`];
  return [`Unerwartete Antwort (HTTP ${status})`];
}

// Fehler aus buildPayload -> Zeilen für dieselbe Fehlerliste.
export function formatClientErrors(errors) {
  return errors.map((e) => `${fieldLabel(e.field)}: ${e.msg}`);
}

// Zahl mit fester Anzahl Nachkommastellen und deutschem Komma.
// Nur für die Anzeige; gesendet und gespeichert wird ungerundet.
export function formatNumber(value, digits) {
  return value.toFixed(digits).replace(".", ",");
}

// Stabilitätswerte aus RocketRead -> Zeilen { label, text }.
// Ohne Bewertung: nur Zahlen, kein „stabil“ oder „instabil“.
// null (keine Geometrie) -> leere Liste.
export function formatStability(stability) {
  if (!stability) return [];
  const mm = (v) => `${formatNumber(fromSI(v, "mm"), 1)} mm`;
  const cal = (v) => `${formatNumber(v, 2)} Kaliber`;
  return [
    { label: "Druckpunkt ab Nasenspitze", text: mm(stability.x_cp) },
    { label: "Schwerpunkt beim Start ab Nasenspitze", text: mm(stability.x_cg_start) },
    { label: "Schwerpunkt leer ab Nasenspitze", text: mm(stability.x_cg_empty) },
    { label: "Stabilitätsmaß beim Start", text: cal(stability.margin_start) },
    { label: "Stabilitätsmaß leer", text: cal(stability.margin_empty) },
  ];
}

// --- Flugkurve ---------------------------------------------------------------
// Aus der Antwort von GET /api/flights/{id}/trajectory werden nur Zahlen
// und Texte für das Diagramm berechnet; die Elemente baut app.js (mit
// textContent). Die Kurve wird nicht verändert, nur in Bildkoordinaten
// umgerechnet.

// Zeichenfläche in SVG-Einheiten (viewBox); per CSS auf volle Breite
// skaliert. Ränder für Achsenmarken und Achsentitel.
export const CHART = { width: 600, height: 300, left: 55, right: 15, top: 15, bottom: 45 };

// Schrittweite der Achsenmarken im 1-2-5-Raster, sodass höchstens
// maxTicks Schritte bis max nötig sind. max <= 0 -> Schritt 1.
export function niceStep(max, maxTicks = 5) {
  if (!(max > 0)) return 1;
  const raw = max / maxTicks;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / magnitude;
  const factor = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return factor * magnitude;
}

// Achse von 0 bis zur ersten Marke, die max erreicht: Endwert und Marken mit Text.
// Nachkommastellen aus der Schrittweite (0,5 -> 1 Stelle, 5 -> keine).
// Werte auf diese Stellen gerundet, damit 3 · 0,1 genau 0,3 ergibt und
// nicht 0.30000000000000004. Die Toleranz 1e-9 verhindert eine
// überflüssige Marke, wenn max / step durch Rundung knapp über einer
// ganzen Zahl liegt.
export function axisTicks(max, maxTicks = 5) {
  const step = niceStep(max, maxTicks);
  const count = Math.max(1, Math.ceil(max / step - 1e-9));
  const digits = Math.max(0, -Math.floor(Math.log10(step) + 1e-9));
  const ticks = [];
  for (let i = 0; i <= count; i++) {
    const value = Number((i * step).toFixed(digits));
    ticks.push({ value, text: formatNumber(value, digits) });
  }
  return { end: ticks[count].value, ticks };
}

// Antwort der Flugkurve -> Zeichendaten in Bildkoordinaten.
// x nach rechts = Zeit, y nach oben = Höhe (in SVG wächst y nach unten).
// Ergebnis: path (Linienzug als SVG-Pfad), xTicks/yTicks ({ pos, text }),
// apogee ({ x, y }) = letzter Punkt der Kurve.
export function chartData(trajectory) {
  const { t, h } = trajectory ?? {};
  if (!Array.isArray(t) || !Array.isArray(h) || t.length < 2 || t.length !== h.length) {
    throw new Error("Flugkurve fehlt oder ist unvollständig");
  }
  if (![...t, ...h].every(Number.isFinite)) {
    throw new Error("Flugkurve enthält ungültige Zahlen");
  }
  const { width, height, left, right, top, bottom } = CHART;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const xAxis = axisTicks(Math.max(...t));
  const yAxis = axisTicks(Math.max(...h));
  const x = (value) => left + (value / xAxis.end) * plotW;
  const y = (value) => top + plotH - (value / yAxis.end) * plotH;

  const coords = t.map((ti, i) => `${x(ti).toFixed(2)},${y(h[i]).toFixed(2)}`);
  const last = t.length - 1;
  return {
    path: `M${coords.join(" L")}`,
    xTicks: xAxis.ticks.map((tick) => ({ pos: x(tick.value), text: tick.text })),
    yTicks: yAxis.ticks.map((tick) => ({ pos: y(tick.value), text: tick.text })),
    apogee: { x: x(t[last]), y: y(h[last]) },
  };
}

// Apogäum und Zeitpunkt aus FlightRead als Text, 2 Nachkommastellen.
export function formatApogee(flight) {
  return `Apogäum: ${formatNumber(flight.apogee, 2)} m nach ${formatNumber(flight.t_apogee, 2)} s`;
}