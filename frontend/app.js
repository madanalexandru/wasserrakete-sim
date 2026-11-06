// Bedienoberfläche: baut das Formular, sendet POST /api/rockets und
// zeigt Fehler oder Ergebnis an. Umrechnung und Aufbereitung stehen in
// lib.js; hier nur der Zugriff auf die Seite.
// Texte vom Server werden immer über textContent eingesetzt, nie als HTML.

import {
  GEOMETRY_FIELDS,
  OPTIONAL_FIELDS,
  REQUIRED_FIELDS,
  UNITS,
  buildPayload,
  formatApiErrors,
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

function showErrors(title, lines) {
  errorsBox.replaceChildren();
  const heading = document.createElement("p");
  heading.textContent = title;
  const list = document.createElement("ul");
  for (const line of lines) {
    const item = document.createElement("li");
    item.textContent = line;
    list.append(item);
  }
  errorsBox.append(heading, list);
}

function clearOutput() {
  errorsBox.replaceChildren();
  resultBox.hidden = true;
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
  resultBox.hidden = false;
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

buildFields("required-fields", REQUIRED_FIELDS);
buildFields("optional-fields", OPTIONAL_FIELDS);
buildFields("geometry-fields", GEOMETRY_FIELDS);

// Werte bleiben beim Abwählen stehen, werden dann aber nicht gesendet.
withGeometry.addEventListener("change", () => {
  geometryBox.hidden = !withGeometry.checked;
});
form.addEventListener("submit", submit);