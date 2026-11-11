import { useEffect, useState } from "react";
import { getWeather } from "../weatherApi";
import { beyondForecast, forecastOpening, summarizeWindows, weatherAdvice } from "../weatherPresentation";
import "../weather.css";

export function RiskBadge({ summary, showScore = false }) {
  const level = summary?.severity || "unknown";
  const labels = { high: "Travel may be affected", moderate: "Some weather concerns", low: "No flagged hazards", unknown: "Forecast not available" };
  const partial = level === "low" && summary.complete === false;
  return <span className={`weather-badge weather-${partial ? "unknown" : level}`}>{partial ? "Partial forecast" : labels[level] || labels.unknown}{showScore && summary?.score != null && <strong>{summary.score}/100</strong>}</span>;
}

// Pass an existing forecast to reuse this card beside recommendations or flights.
export default function WeatherSummary({ tripId, trip, forecast, onNavigate }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (forecast !== undefined) return;
    const controller = new AbortController();
    setResult(null); setError("");
    getWeather(tripId, { signal: controller.signal }).then(setResult).catch((err) => {
      if (err.name !== "AbortError") setError(err.message);
    });
    return () => controller.abort();
  }, [tripId, forecast]);
  const data = forecast === undefined ? result?.forecast : forecast;
  const waiting = beyondForecast(trip, data);
  const summary = summarizeWindows(data?.windows);
  const advice = weatherAdvice(summary, data?.mode);
  const opening = forecastOpening(trip);
  const setup = result?.status === "setup_required";
  const completed = result?.monitoring_complete;
  const title = completed ? "Weather checks finished for this trip" : waiting ? "Your forecast will be ready closer to departure" : setup ? "Choose a city for your local forecast"
    : summary.knownHours ? advice.title : error ? "Weather updates are unavailable right now" : "Your trip forecast is on its way";
  const description = completed ? "Open trip weather to view your saved weather updates." : waiting ? `Forecasts start around ${opening.toLocaleDateString("en-US", { month: "long", day: "numeric" })}. ${setup ? "Choose your destination city now so its weather can be checked closer to departure." : "Automatic checks will keep an eye on changes."}`
    : setup ? "Confirm the city you’re visiting to get started. Your trip dates are already saved."
    : summary.knownHours ? advice.advice : "Open trip weather to see available forecasts and check your travel details.";
  return <section className="weather-compact" aria-label="Trip weather summary">
    <div><span className="weather-eyebrow">Weather</span><h2>{title}</h2><p>{description}</p>
      {(result?.status === "stale" || data?.errors?.length > 0) && !waiting && <p className="weather-muted">Showing the last saved forecast while updates are unavailable.</p>}
    </div>
    {onNavigate && <button type="button" className="weather-secondary" onClick={() => onNavigate(`/trips/${tripId}/weather`)}>{completed ? "View updates" : setup ? "Choose city" : "View weather"} →</button>}
  </section>;
}
