// Tests für die Zeichenfunktionen der Flugkurve in frontend/lib.js.
// Ersatzdaten: senkrechter Wurf ohne Luftwiderstand, h = v0·t − g·t²/2.
// Gipfel bei t = v0/g mit h = v0²/(2g); für v0 = 20 m/s von Hand
// nachrechenbar (2,04 s; 20,39 m). Keine Daten aus der Simulation.

import { test } from "node:test";
import assert from "node:assert/strict";

import { CHART, axisTicks, chartData, formatApogee, niceStep } from "../frontend/lib.js";

const G = 9.80665;
const V0 = 20;
const T_TOP = V0 / G;
const H_TOP = (V0 * V0) / (2 * G);

// Wurfparabel bis zum Gipfel in n gleichen Schritten, Form wie TrajectoryRead.
function parabola(n = 200) {
  const t = [];
  const h = [];
  const v = [];
  for (let i = 0; i <= n; i++) {
    const ti = i === n ? T_TOP : (T_TOP * i) / n;
    t.push(ti);
    h.push(i === n ? H_TOP : V0 * ti - 0.5 * G * ti * ti);
    v.push(i === n ? 0 : V0 - G * ti);
  }
  return { flight_id: 1, model_version: "1", t, h, v };
}

// Pfad "Mx,y Lx,y ..." -> Liste von [x, y]
function pathPoints(path) {
  assert.ok(path.startsWith("M"));
  return path.slice(1).split(" L").map((p) => p.split(",").map(Number));
}

const PLOT_LEFT = CHART.left;
const PLOT_RIGHT = CHART.width - CHART.right;
const PLOT_TOP = CHART.top;
const PLOT_BOTTOM = CHART.height - CHART.bottom;

// --- Achsenmarken ------------------------------------------------------------

test("niceStep: 1-2-5-Raster", () => {
  assert.equal(niceStep(20.39), 5); // 20,39/5 = 4,08 -> 5
  assert.equal(niceStep(2.039), 0.5); // 0,408 -> 0,5
  assert.equal(niceStep(10), 2); // 2 -> 2
  assert.equal(niceStep(7), 2); // 1,4 -> 2
  assert.equal(niceStep(5), 1); // 1 -> 1
  assert.equal(niceStep(300), 100); // 60 -> 100
  assert.equal(niceStep(0.03), 0.01); // 0,006 -> 0,01
});

test("niceStep: Höchstwert 0 oder ungültig -> Schritt 1", () => {
  assert.equal(niceStep(0), 1);
  assert.equal(niceStep(-3), 1);
  assert.equal(niceStep(NaN), 1);
});

test("axisTicks: Gipfelhöhe der Parabel -> 0 bis 25 in Fünferschritten", () => {
  const axis = axisTicks(H_TOP);
  assert.equal(axis.end, 25);
  assert.deepEqual(axis.ticks.map((tick) => tick.text), ["0", "5", "10", "15", "20", "25"]);
});

test("axisTicks: Gipfelzeit -> eine Nachkommastelle mit Komma", () => {
  const axis = axisTicks(T_TOP);
  assert.equal(axis.end, 2.5);
  assert.deepEqual(
    axis.ticks.map((tick) => tick.text),
    ["0,0", "0,5", "1,0", "1,5", "2,0", "2,5"],
  );
});

test("axisTicks: Ende liegt immer auf oder über dem Höchstwert", () => {
  for (const max of [0.001, 0.3, 1, 2.039, 9.99, 10, 10.01, 49, 123.4, 1e4]) {
    const { end, ticks } = axisTicks(max);
    assert.ok(end >= max, `Ende ${end} < ${max}`);
    assert.ok(ticks.length <= 6, `zu viele Marken für ${max}`);
    assert.equal(ticks[0].value, 0);
  }
});

test("axisTicks: Höchstwert genau auf einer Marke -> keine Marke darüber", () => {
  assert.equal(axisTicks(25).end, 25);
  assert.equal(axisTicks(0.3).end, 0.3);
  assert.equal(axisTicks(0.3).ticks.at(-1).text, "0,3");
});

test("axisTicks: Rundungsrest im Höchstwert ergibt keine zusätzliche Marke", () => {
  // 3 · 0,1 = 0.30000000000000004; ohne Toleranz käme eine Marke 0,4 dazu
  const axis = axisTicks(3 * 0.1);
  assert.equal(axis.end, 0.3);
  assert.equal(axis.ticks.length, 4);
});

test("axisTicks: Höchstwert 0 -> Achse bis 1 (keine Division durch null)", () => {
  assert.equal(axisTicks(0).end, 1);
});

// --- Zeichendaten ------------------------------------------------------------

test("chartData: ein Pfadpunkt pro Punkt der Kurve", () => {
  const data = parabola(200);
  assert.equal(pathPoints(chartData(data).path).length, 201);
});

test("chartData: Start (0, 0) links unten in der Zeichenfläche", () => {
  const [x0, y0] = pathPoints(chartData(parabola()).path)[0];
  assert.equal(x0, PLOT_LEFT);
  assert.equal(y0, PLOT_BOTTOM);
});

test("chartData: alle Punkte innerhalb der Zeichenfläche", () => {
  for (const [x, y] of pathPoints(chartData(parabola()).path)) {
    assert.ok(x >= PLOT_LEFT && x <= PLOT_RIGHT, `x = ${x}`);
    assert.ok(y >= PLOT_TOP && y <= PLOT_BOTTOM, `y = ${y}`);
  }
});

test("chartData: Höhe nach oben (höhere Punkte haben kleineres y)", () => {
  const points = pathPoints(chartData(parabola()).path);
  // Parabel steigt bis zum Gipfel: y muss fallen
  assert.ok(points.every((p, i) => i === 0 || p[1] < points[i - 1][1]));
});

test("chartData: Zeit nach rechts", () => {
  const points = pathPoints(chartData(parabola()).path);
  assert.ok(points.every((p, i) => i === 0 || p[0] > points[i - 1][0]));
});

test("chartData: Apogäum = letzter Punkt, Lage von Hand nachgerechnet", () => {
  const { apogee, path } = chartData(parabola());
  const plotW = PLOT_RIGHT - PLOT_LEFT;
  const plotH = PLOT_BOTTOM - PLOT_TOP;
  // Achsen bis 2,5 s und 25 m (siehe axisTicks-Tests)
  const x = PLOT_LEFT + (T_TOP / 2.5) * plotW;
  const y = PLOT_BOTTOM - (H_TOP / 25) * plotH;
  assert.ok(Math.abs(apogee.x - x) < 1e-9);
  assert.ok(Math.abs(apogee.y - y) < 1e-9);
  const [lx, ly] = pathPoints(path).at(-1);
  assert.ok(Math.abs(lx - apogee.x) <= 0.005 && Math.abs(ly - apogee.y) <= 0.005);
});

test("chartData: Achsenmarken an den richtigen Stellen", () => {
  const { xTicks, yTicks } = chartData(parabola());
  assert.equal(xTicks[0].pos, PLOT_LEFT);
  assert.equal(xTicks.at(-1).pos, PLOT_RIGHT);
  assert.equal(xTicks.at(-1).text, "2,5");
  assert.equal(yTicks[0].pos, PLOT_BOTTOM);
  assert.equal(yTicks.at(-1).pos, PLOT_TOP);
  assert.equal(yTicks.at(-1).text, "25");
});

test("chartData: Kurve ohne Steigen (Höhe überall 0) zeichnet ohne Fehler", () => {
  const data = { t: [0, 0.1, 0.2], h: [0, 0, 0], v: [0, 0, 0] };
  const { apogee } = chartData(data);
  assert.equal(apogee.y, PLOT_BOTTOM);
});

test("chartData: fehlende oder unvollständige Kurve -> Fehler", () => {
  assert.throws(() => chartData(null), /fehlt/);
  assert.throws(() => chartData({}), /fehlt/);
  assert.throws(() => chartData({ t: [0], h: [0] }), /fehlt/);
  assert.throws(() => chartData({ t: [0, 1], h: [0] }), /fehlt/);
});

test("chartData: ungültige Zahlen -> Fehler", () => {
  assert.throws(() => chartData({ t: [0, NaN], h: [0, 1] }), /ungültige/);
  assert.throws(() => chartData({ t: [0, 1], h: [0, Infinity] }), /ungültige/);
  assert.throws(() => chartData({ t: [0, 1], h: [0, null] }), /ungültige/);
});

test("chartData: verändert die Eingabe nicht", () => {
  const data = parabola(10);
  const copy = structuredClone(data);
  chartData(data);
  assert.deepEqual(data, copy);
});

// --- Apogäum als Text --------------------------------------------------------

test("formatApogee: zwei Nachkommastellen mit Komma", () => {
  assert.equal(
    formatApogee({ apogee: H_TOP, t_apogee: T_TOP }),
    "Apogäum: 20,39 m nach 2,04 s",
  );
});