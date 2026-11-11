// Presentation helpers keep missing forecasts distinct from reassuring weather.
export const severityRank = { unknown: -1, low: 0, moderate: 1, high: 2 };
export const conditionNames = {
  thunderstorm: "Thunderstorms", freezing_precipitation: "Freezing rain", snow: "Snow",
  rain: "Rain", visibility: "Low visibility", wind: "Wind",
};
export const hazardName = (hazard) => {
  if (hazard.type === "rain" && hazard.severity === "high") return "Heavy rain";
  if (hazard.type === "snow" && hazard.severity === "high") return "Heavy snow";
  if (hazard.type === "wind") return hazard.severity === "high" ? "Strong winds" : "Gusty winds";
  return conditionNames[hazard.type] || hazard.type;
};
export const shortCity = (location) => location?.label?.split(",")[0] || "Your destination";
export const formatDay = (value) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(`${value}T12:00:00`));
export const formatMoment = (value, timezone) => value ? new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
  ...(timezone ? { timeZone: timezone } : {}),
}).format(new Date(value)) : "Not yet checked";
export const localDay = (value, timezone) => new Intl.DateTimeFormat("en-CA", {
  year: "numeric", month: "2-digit", day: "2-digit", timeZone: timezone,
}).format(new Date(value));
export const display = (value, convert = (n) => n, suffix = "") => value == null ? "—" : `${Math.round(convert(value) * 10) / 10}${suffix}`;

export function forecastOpening(trip) {
  if (!trip?.start_date) return null;
  const date = new Date(`${trip.start_date}T12:00:00`);
  date.setDate(date.getDate() - 15);
  return date;
}

export function beyondForecast(trip, forecast, now = new Date()) {
  if (forecast?.windows?.some((w) => w.rows.some((r) => r.score != null && new Date(r.time) >= now))) return false;
  const date = forecastOpening(trip);
  if (!date) return false;
  return date.toDateString() !== now.toDateString() && date > now;
}

export function summarizeWindows(windows = [], now = new Date()) {
  const cutoff = Math.floor(new Date(now).getTime() / 3600000) * 3600000;
  const rows = windows.flatMap((w) => w.rows || []).filter((r) => new Date(r.time).getTime() >= cutoff);
  const known = rows.filter((r) => r.score != null);
  const hazards = new Map();
  for (const row of known) for (const hazard of row.hazards || []) {
    if (!hazards.has(hazard.type) || severityRank[hazard.severity] > severityRank[hazards.get(hazard.type).severity]) hazards.set(hazard.type, hazard);
  }
  const severity = known.reduce((level, r) => severityRank[r.severity] > severityRank[level] ? r.severity : level, "unknown");
  const concern = windows.flatMap((w) => (w.rows || []).map((r) => ({ ...r, location: w.location })))
    .filter((r) => new Date(r.time).getTime() >= cutoff && r.severity === severity && r.hazards?.length)
    .sort((a, b) => new Date(a.time) - new Date(b.time))[0];
  return { severity, score: known.length ? Math.max(...known.map((r) => r.score)) : null,
    complete: !!windows.length && windows.every((w) => w.status === "available" || (w.status === "stale" && w.summary?.complete)) && !!rows.length && rows.every((r) => r.complete),
    hazards: [...hazards.values()], concern, rows, knownHours: known.length };
}

export function journeyGroups(forecast, trip, origin, now = new Date()) {
  const windows = (forecast?.windows || []).filter((w) => new Date(w.end) > now);
  return [
    { key: "outbound", title: "Getting there", date: trip?.start_date, windows: windows.filter((w) => w.key.startsWith("outbound")) },
    { key: "stay", title: "At your destination", date: trip?.start_date, windows: windows.filter((w) => w.category === "stay") },
    { key: "return", title: "Coming home", date: trip?.end_date, windows: windows.filter((w) => w.key.startsWith("return")) },
  ].filter((group) => group.windows.length).map((group) => {
    const summary = summarizeWindows(group.windows, now);
    if (!origin && group.key !== "stay") summary.complete = false;
    if (forecast.mode === "driving" && group.key !== "stay" && forecast.routes?.[group.key]?.status !== "available") summary.complete = false;
    return { ...group, summary };
  });
}

export function weatherAdvice(summary, mode = "flight") {
  if (!summary?.knownHours) return { title: "We’re waiting for your forecast", advice: "Available weather will appear here after the next check." };
  if (!summary.complete && !summary.hazards.length) return {
    title: "Part of your forecast is ready", advice: "We’re still waiting for some weather details. You can view what’s available below.",
  };
  const names = summary.hazards.map(hazardName);
  if (!names.length) return { title: "No major weather hazards flagged", advice: "Nothing in the available forecast currently suggests a major weather disruption. We’ll keep checking as your trip approaches." };
  const main = Object.keys(conditionNames).find((kind) => summary.hazards.some((h) => h.type === kind));
  const title = `${hazardName(summary.hazards.find((h) => h.type === main))} to watch on your trip`;
  let advice = mode === "flight" ? "Check your airline’s updates before heading to the airport, and allow extra travel time." : "Allow extra travel time and check local road conditions before setting off.";
  if (main === "snow" || main === "freezing_precipitation") advice = mode === "flight"
    ? "Allow extra time for travel to the airport and possible deicing. Check your airline before you leave."
    : "Check local road conditions before leaving; snow or ice may affect your route.";
  return { title, advice };
}

export function temperatureRange(rows = []) {
  const temps = rows.map((r) => r.temperature_2m).filter((t) => t != null).map((t) => t * 9 / 5 + 32);
  if (!temps.length) return null;
  return `${Math.round(Math.min(...temps))}–${Math.round(Math.max(...temps))}°F`;
}

export function updateCopy(event) {
  const changes = event.detail?.changes || [];
  const improved = changes.length && changes.every((c) => severityRank[c.severity] < severityRank[c.previous_severity]);
  const key = event.detail?.window || "";
  const where = key.startsWith("outbound") ? "your journey there" : key.startsWith("return") ? "your journey home" : "your destination";
  return { title: improved ? `Weather looks better for ${where}` : `Weather changed for ${where}`,
    detail: improved ? "Previously flagged weather concerns have eased in the latest forecast." : "The latest forecast has different weather conditions. Take another look before you travel." };
}

export function sameWeatherPlan(left, right) {
  if (!left || !right) return false;
  const key = (plan) => JSON.stringify({
    mode: plan.mode,
    origin: plan.origin ? [plan.origin.latitude, plan.origin.longitude, plan.origin.label, plan.origin.timezone] : null,
    destination: plan.destination ? [plan.destination.latitude, plan.destination.longitude, plan.destination.label, plan.destination.timezone] : null,
    outbound: plan.outbound_time || null, returning: plan.return_time || null,
  });
  return key(left) === key(right);
}
