import test from "node:test";
import assert from "node:assert/strict";
import { beyondForecast, forecastOpening, summarizeWindows, weatherAdvice, journeyGroups, hazardName, updateCopy, sameWeatherPlan } from "../src/weatherPresentation.js";

const now = new Date("2026-11-11T18:30:00Z");
const location = { label: "Denver, Colorado, United States", timezone: "America/Denver" };
const row = (values = {}) => ({ time: "2026-11-13T18:00:00Z", score: 0, severity: "low", complete: true, hazards: [], ...values });
const window = (values = {}) => ({ key: "stay", category: "stay", start: "2026-11-13T00:00:00Z", end: "2026-11-14T00:00:00Z", status: "available", location, rows: [row()], ...values });

test("distant trips get a calendar date instead of an empty risk assessment", () => {
  const trip = { start_date: "2026-12-05" };
  assert.equal(beyondForecast(trip, { windows: [window({ rows: [] })] }, now), true);
  const opens = forecastOpening(trip);
  assert.equal(opens.getMonth(), 10);
  assert.equal(opens.getDate(), 20);
  assert.equal(beyondForecast({ start_date: "2026-11-13" }, null, now), false);
});

test("forecast opening dates work across the year boundary", () => {
  const date = forecastOpening({ start_date: "2027-01-05" });
  assert.equal(date.getFullYear(), 2026);
  assert.equal(date.getMonth(), 11);
  assert.equal(date.getDate(), 21);
});

test("missing risk data is distinct from a reassuring forecast", () => {
  const summary = summarizeWindows([window({ rows: [row({ score: null, severity: "unknown", complete: false })], status: "partial" })], now);
  assert.equal(summary.knownHours, 0);
  assert.equal(summary.score, null);
  assert.equal(summary.severity, "unknown");
  assert.match(weatherAdvice(summary).title, /waiting/);
});

test("partial observations with no flags do not claim a clear forecast", () => {
  const summary = summarizeWindows([window({ rows: [row({ complete: false })], status: "partial" })], now);
  assert.equal(summary.complete, false);
  assert.equal(weatherAdvice(summary).title, "Part of your forecast is ready");
});

test("expired storms do not dominate the current journey summary", () => {
  const storm = { type: "thunderstorm", severity: "high" };
  const summary = summarizeWindows([window({ rows: [row({ time: "2026-11-11T10:00:00Z", severity: "high", score: 40, hazards: [storm] }), row()] })], now);
  assert.equal(summary.severity, "low");
  assert.equal(summary.hazards.length, 0);
});

test("known hazards retain their place and time and give travel-specific advice", () => {
  const summary = summarizeWindows([window({ rows: [row({ severity: "high", score: 40, hazards: [{ type: "thunderstorm", severity: "high" }] })] })], now);
  assert.equal(summary.concern.location.label, location.label);
  assert.equal(summary.concern.time, "2026-11-13T18:00:00Z");
  assert.match(weatherAdvice(summary, "flight").advice, /airline/);
  assert.match(weatherAdvice(summary, "driving").advice, /road conditions/);
});

test("travel groups stay incomplete when a departure city or road route is missing", () => {
  const windows = [window({ key: "outbound_arrival", category: "flight" }), window()];
  const flight = journeyGroups({ mode: "flight", windows }, {}, null, now);
  assert.equal(flight.find((g) => g.key === "outbound").summary.complete, false);
  assert.equal(flight.find((g) => g.key === "stay").summary.complete, true);
  const drive = journeyGroups({ mode: "driving", routes: { outbound: { status: "unavailable" } }, windows }, {}, location, now);
  assert.equal(drive.find((g) => g.key === "outbound").summary.complete, false);
});

test("rain and wind wording respects the actual hazard severity", () => {
  assert.equal(hazardName({ type: "rain", severity: "moderate" }), "Rain");
  assert.equal(hazardName({ type: "rain", severity: "high" }), "Heavy rain");
  assert.equal(hazardName({ type: "wind", severity: "moderate" }), "Gusty winds");
});

test("improvements are explained as improvements, not another alarming change", () => {
  const copy = updateCopy({ detail: { window: "outbound_departure", changes: [{ previous_severity: "high", severity: "low" }] } });
  assert.match(copy.title, /better/);
  assert.match(copy.title, /journey there/);
});

test("saving unchanged details does not need another provider refresh", () => {
  const plan = { mode: "flight", origin: null, destination: { ...location, latitude: 39.74, longitude: -104.99 }, outbound_time: null, return_time: null };
  const draft = { ...plan, destination: { ...plan.destination, id: 123, name: "Denver" }, outbound_time: "", return_time: "" };
  assert.equal(sameWeatherPlan(plan, draft), true);
  assert.equal(sameWeatherPlan(plan, { ...draft, mode: "driving" }), false);
});

test("a complete saved forecast keeps its coverage separate from its age", () => {
  const summary = summarizeWindows([window({ status: "stale", summary: { complete: true } })], now);
  assert.equal(summary.complete, true);
  assert.equal(summary.knownHours, 1);
});
