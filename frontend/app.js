// Bedienoberfläche: baut das Formular, sendet POST /api/rockets und
// zeigt Fehler oder Ergebnis an. Danach kann für die angelegte Rakete ein
// Flug simuliert werden: POST /api/rockets/{id}/flights, dann
// GET /api/flights/{id}/trajectory für das Diagramm.
// Umrechnung und Aufbereitung stehen in lib.js; hier nur der Zugriff auf
// die Seite. Texte vom Server werden immer über textContent eingesetzt,
// nie als HTML.

import {
  CHART,
  GEOMETRY_FIELDS,
  OPTIONAL_FIELDS,
  REQUIRED_FIELDS,
  UNITS,
  buildPayload,
  chartData,
  formatApiErrors,
  formatApogee,
  formatClientErrors,
  formatStability,
} from "./lib.js";

// Anzeigenamen für Auswahlwerte; gesendet wird der Wert der API.
const CHOICE_LABELS = { cone: "Kegel", ogive: "Ogive" };

const form = document.getElementById("rocket-form");
const withGeometry = document.getElementById("with-geometry");
const geometryBox = document.getElementById("geometry");
const submitButton = document.getElementById("submit");
const errorsBox = document.getElementById("errors");
const resultBox = document.getElementById("result");
const flyButton = document.getElementById("fly");
const flightErrorsBox = document.getElementById("flight-errors");
const flightBox = document.getElementById("flight");
const chart = document.getElementById("chart");

const SVG_NS = "http://www.w3.org/2000/svg";

// ID der angezeigten Rakete; null, solange keine angezeigt wird.
let currentRocketId = null;

// Eine Zeile des Formulars: Bezeichnung, Eingabe, Einheit.
function buildField(f) {
  const row = document.createElement("div");
  row.className = "field";

  const label = document.createElement("label");
  label.htmlFor = f.api;
  label.textContent = f.label;

  let input;
  if (f.kind === "choice") {
    input = document.createElement("select");
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "– bitte wählen –";
    input.append(empty);
    for (const c of f.choices) {
      const option = document.createElement("option");
      option.value = String(c);
      option.textContent = CHOICE_LABELS[c] ?? String(c);
      input.append(option);
    }
  } else {
    // Textfeld statt type="number": Komma und Punkt sind erlaubt, und
    // eine ungültige Eingabe kommt als Text an, statt still leer zu sein.
    input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
  }
  input.id = f.api;
  input.name = f.api;

  const unit = document.createElement("span");
  unit.textContent = f.kind === "choice" ? "" : UNITS[f.unit].label;

  row.append(label, input, unit);
  return row;
}

function buildFields(containerId, fields) {
  const container = document.getElementById(containerId);
  for (const f of fields) container.append(buildField(f));
}

// Alle Eingaben als Texte, Schlüssel = Feldname der API.
// Zugriff über die ID: form.elements.name könnte mit eingebauten
// Eigenschaften des Formulars verwechselt werden.
function readForm() {
  const values = { name: document.getElementById("name").value };
  for (const f of [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS, ...GEOMETRY_FIELDS]) {
    values[f.api] = document.getElementById(f.api).value;
  }
  return values;
}

// Fehlerliste in box (Standard: unter dem Formular).
function showErrors(title, lines, box = errorsBox) {
  box.replaceChildren();
  const heading = document.createElement("p");
  heading.textContent = title;
  const list = document.createElement("ul");
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    list.append(item);
  }
  box.append(heading, list);
}

function clearOutput() {
  errorsBox.replaceChildren();
  resultBox.hidden = true;
  currentRocketId = null;
}

function clearFlight() {
  flightErrorsBox.replaceChildren();
  flightBox.hidden = true;
  chart.replaceChildren();
}

function showResult(rocket) {
  document.getElementById("result-head").textContent =
    `Rakete „${rocket.name}“ gespeichert, ID ${rocket.id}.`;

  const table = document.getElementById("stability");
  table.replaceChildren();
  const rows = formatStability(rocket.stability);
  for (const { label, text } of rows) {
    const tr = document.createElement("tr");
    const tdLabel = document.createElement("td");
    tdLabel.textContent = label;
    const tdValue = document.createElement("td");
    tdValue.textContent = text;
    tr.append(tdLabel, tdValue);
    table.append(tr);
  }
  document.getElementById("stability-note").textContent = rows.length
    ? "Stabilitätswerte nach Barrowman, berechnet, ohne Bewertung."
    : "Keine Geometrie angegeben, daher keine Stabilitätswerte.";
  clearFlight();
  currentRocketId = rocket.id;
  resultBox.hidden = false;
}

// SVG-Element mit Attributen; Texte nur über textContent.
function svgElement(name, attributes, text) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    el.setAttribute(key, String(value));
  }
  if (text !== undefined) el.textContent = text;
  return el;
}

// Zeichendaten aus chartData -> Elemente im SVG (ersetzt das alte Diagramm).
function drawChart(data) {
  const { width, height, left, right, top, bottom } = CHART;
  const xEnd = width - right;
  const yEnd = height - bottom;
  const yMid = (top + yEnd) / 2;
  const parts = [];
  for (const { pos, text } of data.yTicks) {
    parts.push(svgElement("line", { class: "grid", x1: left, x2: xEnd, y1: pos, y2: pos }));
    parts.push(svgElement("text", { x: left - 6, y: pos + 5, "text-anchor": "end" }, text));
  }
  for (const { pos, text } of data.xTicks) {
    parts.push(svgElement("line", { class: "grid", x1: pos, x2: pos, y1: top, y2: yEnd }));
    parts.push(svgElement("text", { x: pos, y: yEnd + 18, "text-anchor": "middle" }, text));
  }
  parts.push(
    svgElement("line", { class: "axis", x1: left, x2: xEnd, y1: yEnd, y2: yEnd }),
    svgElement("line", { class: "axis", x1: left, x2: left, y1: top, y2: yEnd }),
    svgElement(
      "text",
      { x: (left + xEnd) / 2, y: height - 4, "text-anchor": "middle" },
      "Zeit in s",
    ),
    svgElement(
      "text",
      { x: 14, y: yMid, "text-anchor": "middle", transform: `rotate(-90 14 ${yMid})` },
      "Höhe in m",
    ),
    svgElement("path", { class: "curve", d: data.path }),
  );
  const { x, y } = data.apogee;
  const marker = svgElement("circle", { class: "apogee", cx: x, cy: y, r: 5 });
  marker.append(svgElement("title", {}, "Apogäum"));
  parts.push(marker);
  chart.replaceChildren(...parts);
}

function showFlight(flight) {
  document.getElementById("flight-head").textContent =
    `Flug ${flight.id} gespeichert (Modellversion ${flight.model_version}).`;
  document.getElementById("apogee").textContent = formatApogee(flight);
  chart.replaceChildren();
  flightBox.hidden = false;
}

// Antwort lesen: JSON, wenn möglich, sonst null (z. B. Textseite bei 500/502).
async function readBody(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function submit(event) {
  event.preventDefault();
  clearOutput();

  const { payload, errors } = buildPayload(readForm(), withGeometry.checked);
  if (errors.length > 0) {
    showErrors("Bitte Eingaben prüfen:", formatClientErrors(errors));
    return;
  }

  // Gesperrt während der Anfrage, damit ein Doppelklick nicht zwei
  // Raketen anlegt.
  submitButton.disabled = true;
  try {
    const response = await fetch("/api/rockets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await readBody(response);
    if (response.status === 201 && body) {
      showResult(body);
    } else {
      showErrors(`Vom Server abgelehnt (HTTP ${response.status}):`, formatApiErrors(response.status, body));
    }
  } catch {
    showErrors("Keine Verbindung zum Server:", ["Anfrage konnte nicht gesendet werden."]);
  } finally {
    submitButton.disabled = false;
  }
}

// Flug der angezeigten Rakete rechnen und anzeigen, dann die Flugkurve.
// Scheitert nur die Kurve, bleiben Flug und Apogäum stehen.
// Wird währenddessen eine andere Rakete angelegt, wird die Antwort verworfen.
async function simulate() {
  const rocketId = currentRocketId;
  if (rocketId === null) return;
  clearFlight();
  // Gesperrt während der Anfrage, damit ein Doppelklick nicht zwei Flüge anlegt.
  flyButton.disabled = true;
  try {
    const response = await fetch(`/api/rockets/${rocketId}/flights`, { method: "POST" });
    const flight = await readBody(response);
    if (rocketId !== currentRocketId) return;
    if (response.status !== 201 || !flight) {
      showErrors(
        `Flug vom Server abgelehnt (HTTP ${response.status}):`,
        formatApiErrors(response.status, flight),
        flightErrorsBox,
      );
      return;
    }
    showFlight(flight);

    const curveResponse = await fetch(`/api/flights/${flight.id}/trajectory`);
    const trajectory = await readBody(curveResponse);
    if (rocketId !== currentRocketId) return;
    if (curveResponse.status !== 200 || !trajectory) {
      showErrors(
        `Flugkurve nicht abrufbar (HTTP ${curveResponse.status}):`,
        formatApiErrors(curveResponse.status, trajectory),
        flightErrorsBox,
      );
      return;
    }
    try {
      drawChart(chartData(trajectory));
    } catch (err) {
      showErrors("Flugkurve nicht darstellbar:", [err.message], flightErrorsBox);
    }
  } catch {
    if (rocketId !== currentRocketId) return;
    const lines = ["Anfrage konnte nicht gesendet werden."];
    showErrors("Keine Verbindung zum Server:", lines, flightErrorsBox);
  } finally {
    flyButton.disabled = false;
  }
}

buildFields("required-fields", REQUIRED_FIELDS);
buildFields("optional-fields", OPTIONAL_FIELDS);
buildFields("geometry-fields", GEOMETRY_FIELDS);

// Werte bleiben beim Abwählen stehen, werden dann aber nicht gesendet.
withGeometry.addEventListener("change", () => {
  geometryBox.hidden = !withGeometry.checked;
});
form.addEventListener("submit", submit);
flyButton.addEventListener("click", simulate);