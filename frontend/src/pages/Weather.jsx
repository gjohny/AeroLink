import { useEffect, useRef, useState } from "react";
import DestinationAutocomplete from "../components/DestinationAutocomplete";
import { RiskBadge } from "../components/WeatherSummary";
import { getWeatherTrip, getWeatherPlan, saveWeatherPlan, getWeather, refreshWeather, getWeatherEvents, readWeatherEvent } from "../weatherApi";
import { shortCity, formatDay, formatMoment, localDay, display, forecastOpening, beyondForecast,
  summarizeWindows, journeyGroups, weatherAdvice, temperatureRange, hazardName, updateCopy, sameWeatherPlan } from "../weatherPresentation";
import "../weather.css";

const emptyPlan = { destination: null, origin: null, mode: "flight", outbound_time: "", return_time: "" };

function TemperatureChart({ rows, location }) {
  const valid = rows.filter((row) => row.temperature_2m != null);
  if (!valid.length || !location) return null;
  const day = localDay(valid[0].time, location.timezone);
  const hours = valid.filter((row) => localDay(row.time, location.timezone) === day);
  const temperatures = hours.map((row) => row.temperature_2m * 9 / 5 + 32);
  const low = Math.min(...temperatures), high = Math.max(...temperatures);
  const start = new Date(hours[0].time).getTime(), end = new Date(hours.at(-1).time).getTime();
  const points = hours.map((row, index) => `${4 + (new Date(row.time).getTime() - start) / (end - start || 1) * 272},${68 - (temperatures[index] - low) / (high - low || 1) * 50}`).join(" ");
  const clock = (value) => new Intl.DateTimeFormat("en-US", { hour: "numeric", timeZone: location.timezone }).format(new Date(value));
  return <figure className="weather-temperature">
    <figcaption>{shortCity(location)} <span>· {formatDay(day)}</span></figcaption>
    <div className="weather-temperature-value">{Math.round(low)}{Math.round(low) !== Math.round(high) && `–${Math.round(high)}`}<span>°F</span></div>
    {hours.length > 1 && <><svg viewBox="0 0 280 80" role="img" aria-label={`Hourly temperature forecast in ${shortCity(location)} for ${formatDay(day)}`}><path d="M4 77H276" fill="none" stroke="currentColor" className="weather-chart-rule" /><polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" /></svg>
      <div className="weather-chart-hours"><span>{clock(hours[0].time)}</span><span>Local time</span><span>{clock(hours.at(-1).time)}</span></div></>}
  </figure>;
}

function ForecastWindow({ item }) {
  const [day, setDay] = useState("");
  const upcoming = item.rows.filter((row) => new Date(row.time) >= Math.floor(Date.now() / 3600000) * 3600000);
  const days = [...new Set(upcoming.map((row) => localDay(row.time, item.location.timezone)))];
  const selectedDay = days.includes(day) ? day : days[0];
  const rows = upcoming.filter((row) => localDay(row.time, item.location.timezone) === selectedDay);
  const label = item.category === "stay" ? "Destination forecast" : item.key.endsWith("departure") ? "Departure city" : "Arrival city";
  return <section className="weather-window">
    <h4>{label}: {shortCity(item.location)}</h4>
    {!rows.length ? <p className="weather-muted">Forecasts for this part of your trip aren’t available yet.</p> : <>
      <label className="weather-day-select">Choose a day<select value={selectedDay} onChange={(e) => setDay(e.target.value)}>{days.map((d) => <option key={d} value={d}>{formatDay(d)}</option>)}</select></label>
      {item.status !== "available" && <p className="weather-muted">{item.status === "stale" ? "Showing the last saved forecast while updates are unavailable." : "Some hours or measurements are not available yet."}</p>}
      <div className="weather-table-scroll"><table><caption>Local times in {shortCity(item.location)}. A dash means data isn’t available.</caption>
        <thead><tr><th>Time</th><th>Temperature</th><th>Rain chance</th><th>Rain</th><th>Snow</th><th>Visibility</th><th>Wind / gust</th><th>Weather</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.time}><th scope="row">{formatMoment(row.time, item.location.timezone)}</th>
          <td>{display(row.temperature_2m, (v) => v * 9 / 5 + 32, "°F")}</td><td>{display(row.precipitation_probability, undefined, "%")}</td>
          <td>{display(row.rain, (v) => v / 25.4, " in/h")}</td><td>{display(row.snowfall, (v) => v / 2.54, " in/h")}</td>
          <td>{display(row.visibility, (v) => v / 1609.344, " mi")}</td><td>{display(row.wind_speed_10m, (v) => v / 1.609344)} / {display(row.wind_gusts_10m, (v) => v / 1.609344, " mph")}</td>
          <td>{row.hazards.map(hazardName).join(", ") || (row.complete ? "No flagged hazards" : "Partial forecast")}</td></tr>)}</tbody>
      </table></div>
    </>}
  </section>;
}

function RouteDetails({ leg, route, windows }) {
  const coords = route?.geometry?.coordinates || [];
  const longs = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
  const minX = Math.min(...longs), maxX = Math.max(...longs), minY = Math.min(...lats), maxY = Math.max(...lats);
  const points = coords.map(([x, y]) => `${20 + (x - minX) / (maxX - minX || 1) * 460},${160 - (y - minY) / (maxY - minY || 1) * 140}`).join(" ");
  return <div className="weather-route-detail">
    {route?.status === "available" ? <>
      <p>{display(route.distance_m, (v) => v / 1609.344, " miles")} · About {display(route.duration_seconds, (v) => v / 3600, " hours of driving")}</p>
      <svg className="weather-route-map" viewBox="0 0 500 180" role="img" aria-label={`${leg} road route overview`}><polyline points={points} fill="none" stroke="currentColor" strokeWidth="3" /></svg>
      <p className="weather-muted">Travel times exclude traffic and stops. Times below use the departure city’s timezone.</p>
    </> : <p className="weather-note">We couldn’t load the road route. Departure and destination forecasts are shown where available.</p>}
    <ol className="weather-route-points">{windows.map((w, index) => <li key={w.key}>
      <div><strong>{index === 0 ? "Setting off" : index === windows.length - 1 ? "Near your destination" : `Along the way · stop ${index + 1}`}</strong><small>{formatMoment(w.eta || w.start, w.location.timezone)}</small></div>
      <RiskBadge summary={w.summary} />
      {w.status !== "available" && <p className="weather-muted">{w.status === "stale" ? "Last saved forecast" : "Some forecast data is unavailable"}</p>}
      {w.summary.hazards.map((h) => <p key={h.type}>{h.reason}</p>)}
    </li>)}</ol>
  </div>;
}

function JourneyCard({ group, forecast, plan }) {
  const { summary } = group;
  const tone = summary.severity === "low" && !summary.complete ? "unknown" : summary.severity;
  const concerns = summary.hazards.map(hazardName);
  const temperature = group.key === "stay" ? temperatureRange(summary.rows) : null;
  const incomplete = !summary.complete && summary.knownHours > 0;
  const index = { outbound: "01", stay: "02", return: "03" }[group.key];
  return <details className={`weather-journey-card weather-card-${tone}`}>
    <summary>
      <span className="weather-journey-index" aria-hidden="true">{index}</span>
      <span className="weather-journey-top"><h3>{group.title}</h3><small>{group.key === "stay" ? shortCity(plan.destination) : formatDay(group.date)}</small></span>
      <span className="weather-journey-description"><span>{concerns.join(" · ") || (summary.knownHours ? temperature || (incomplete ? "Some weather details are still pending" : "No major hazards flagged") : "Forecast available closer to this travel day")}</span>
        {temperature && concerns.length > 0 && <small>{temperature}</small>}
        {incomplete && <small>Partial forecast</small>}
      </span>
      <span className="weather-journey-result"><RiskBadge summary={summary} /><span className="weather-details-link">View forecast <span aria-hidden="true" /></span></span>
    </summary>
    <div className="weather-journey-body">
      {forecast.mode === "driving" && group.key !== "stay"
        ? <RouteDetails leg={group.key} route={forecast.routes?.[group.key]} windows={group.windows} />
        : group.windows.map((item) => <ForecastWindow key={item.key} item={item} />)}
    </div>
  </details>;
}

function WeatherUpdate({ event, onRead }) {
  const copy = updateCopy(event);
  return <article className={`weather-event${event.is_read ? "" : " weather-unread"}`}>
    <div><h3>{copy.title}</h3><p>{copy.detail}</p><small>{formatMoment(event.created_at)}</small>
      <details><summary>See what changed</summary><ul>{event.detail.changes?.map((change) => <li key={change.time}>
        {formatMoment(change.time, event.detail.location?.timezone)}: {change.previous_severity === "low" ? "No flagged hazards" : `${change.previous_severity} concern`} → {change.severity === "low" ? "No flagged hazards" : `${change.severity} concern`}
      </li>)}</ul>{event.detail.high_risk_onset_shift && <p>The higher-risk weather is now expected {formatMoment(event.detail.high_risk_onset_shift.current, event.detail.location?.timezone)}.</p>}</details>
    </div>{!event.is_read && <button className="weather-secondary" type="button" onClick={() => onRead(event.id)}>Got it</button>}
  </article>;
}

export default function Weather({ tripId, onNavigate }) {
  const [trip, setTrip] = useState(null), [plan, setPlan] = useState(null), [draft, setDraft] = useState(emptyPlan);
  const [originText, setOriginText] = useState(""), [destinationText, setDestinationText] = useState("");
  const [result, setResult] = useState(null), [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [editing, setEditing] = useState(false);
  const [changingDestination, setChangingDestination] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [connectionError, setConnectionError] = useState("");
  const alive = useRef(true);
  const applyWeather = (incoming) => setResult((old) => {
    if (old && ((incoming.revision || 0) < (old.revision || 0) ||
      (incoming.revision === old.revision && (incoming.snapshot_id || 0) < (old.snapshot_id || 0)))) return old;
    return incoming;
  });

  function startEditing(saved = plan, currentTrip = trip) {
    const settings = saved || emptyPlan;
    setDraft({ ...settings });
    setOriginText(settings.origin?.label?.slice(0, 200) || "");
    setDestinationText(settings.destination?.label?.slice(0, 200) || currentTrip?.destination || "");
    setChangingDestination(!settings.destination);
    setError(""); setNotice(""); setEditing(true);
  }

  async function checkForecast(announce = true) {
    setBusy(true); setError("");
    if (announce) setNotice("");
    try {
      const data = await refreshWeather(tripId);
      const history = await getWeatherEvents(tripId);
      if (alive.current) {
        applyWeather(data); setEvents(history.events); setConnectionError("");
        if (announce) setNotice(data.refreshing ? "We’re checking your weather. This page will update automatically." : "Weather check complete.");
      }
    } catch (err) { if (alive.current) setError(err.message); }
    finally { if (alive.current) setBusy(false); }
  }

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    Promise.all([getWeatherTrip(tripId, { signal: controller.signal }), getWeather(tripId, { signal: controller.signal })])
      .then(async ([tripData, weather]) => {
        const [settings, history] = await Promise.all([getWeatherPlan(tripId, { signal: controller.signal }), getWeatherEvents(tripId, { signal: controller.signal })]);
        if (!alive.current) return;
        setTrip(tripData.trip); applyWeather(weather); setEvents(history.events); setPlan(settings.plan);
        if (!settings.plan?.destination) startEditing(settings.plan, tripData.trip);
        if (settings.plan?.destination && weather.status === "pending" && !weather.last_attempt_at && !weather.refreshing && !weather.monitoring_complete && !beyondForecast(tripData.trip, weather.forecast)) checkForecast(false);
      }).catch((err) => { if (alive.current && err.name !== "AbortError") setError(err.message); })
      .finally(() => { if (alive.current) setLoading(false); });
    const timer = setInterval(async () => {
      if (document.hidden) return;
      try {
        const [weather, history] = await Promise.all([getWeather(tripId, { signal: controller.signal }), getWeatherEvents(tripId, { signal: controller.signal })]);
        if (alive.current) { applyWeather(weather); setEvents(history.events); setConnectionError(""); }
      } catch (err) { if (alive.current && err.name !== "AbortError") setConnectionError("Updates are temporarily unavailable. We’ll try again; your last saved forecast is still shown below."); }
    }, 30000);
    return () => { alive.current = false; controller.abort(); clearInterval(timer); };
  }, [tripId]);

  async function save(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      if (sameWeatherPlan(draft, plan)) {
        setEditing(false); setNotice("Your trip details are up to date."); return;
      }
      const saved = await saveWeatherPlan(tripId, draft);
      if (!alive.current) return;
      setPlan(saved.plan); setEditing(false);
      const pending = await getWeather(tripId);
      if (!alive.current) return;
      applyWeather(pending);
      if (!beyondForecast(trip, pending.forecast) && !pending.monitoring_complete) await checkForecast(false);
      if (alive.current) setNotice("Trip details saved. Weather checks are scheduled automatically.");
    } catch (err) { if (alive.current) setError(err.message); }
    finally { if (alive.current) setBusy(false); }
  }

  async function markRead(id) {
    try {
      await readWeatherEvent(tripId, id);
      if (alive.current) setEvents((old) => old.map((e) => e.id === id ? { ...e, is_read: true } : e));
    } catch (err) { if (alive.current) setError(err.message); }
  }

  const forecast = result?.forecast;
  const waiting = trip && beyondForecast(trip, forecast);
  const groups = journeyGroups(forecast, trip, plan?.origin);
  const outlook = summarizeWindows(plan?.origin ? forecast?.windows : (forecast?.windows || []).filter((w) => w.category === "stay"));
  const advice = weatherAdvice(outlook, plan?.mode);
  const opening = forecastOpening(trip);
  const destination = shortCity(plan?.destination) === "Your destination" ? trip?.destination : shortCity(plan?.destination);
  const unread = events.filter((e) => !e.is_read);
  const highlighted = unread.slice(0, 3);
  const older = events.filter((e) => !highlighted.some((shown) => shown.id === e.id));
  const invalidOrigin = !!originText.trim() && !draft.origin;
  const draftReady = !!draft.destination && !invalidOrigin && (draft.mode !== "driving" || !!draft.origin);
  const updateDraft = (key, value) => setDraft((old) => ({ ...old, [key]: value }));

  return <section className="weather-page">
    <header className="weather-page-header">
      <button type="button" className="weather-back" onClick={() => onNavigate(`/trips/${tripId}`)}>← Back to trip</button>
      <div className="weather-heading-row"><div><span className="weather-eyebrow">Trip weather</span><h1>{trip ? `Weather for ${destination}` : "Trip weather"}</h1>
        {trip && <p>{formatDay(trip.start_date)} – {formatDay(trip.end_date)}, {trip.end_date.slice(0, 4)}{plan && ` · ${plan.mode === "driving" ? "Driving" : "Flying"}`}</p>}</div>
        {plan && !editing && <button type="button" className="weather-secondary" disabled={busy || result?.refreshing} onClick={() => startEditing()}>Edit journey</button>}
      </div>
    </header>
    {error && <p className="weather-error" role="alert">{error}</p>}
    {notice && <p className="weather-feedback" role="status">{notice}</p>}
    {connectionError && <p className="weather-note" role="status">{connectionError}</p>}
    {loading ? <div className="weather-loading" role="status">Getting your trip weather…</div> : trip && <>
      {editing && <form className="weather-setup" onSubmit={save}>
        <h2>{!draft.destination || !plan?.destination ? "Which city are you visiting?" : "Travel details"}</h2>
        <p>{!plan?.destination ? "Choose the city you’ll stay in for a local forecast. Your trip dates are already filled in." : "Your destination and dates are saved. Add where you’re leaving from to check weather along the journey."}</p>
        <fieldset className="weather-mode-choice"><legend>How are you traveling?</legend>{[["flight", "Flying"], ["driving", "Driving"]].map(([mode, label]) => <button key={mode} type="button" aria-pressed={draft.mode === mode}
          onClick={() => setDraft((old) => ({ ...old, mode, outbound_time: mode === "driving" ? old.outbound_time || "09:00" : "", return_time: mode === "driving" ? old.return_time || "09:00" : "" }))}>{label}</button>)}</fieldset>
        {draft.destination && !changingDestination && <div className="weather-saved-destination"><span><small>Destination</small><strong>{draft.destination.label}</strong></span><button className="weather-text-button" type="button" onClick={() => setChangingDestination(true)}>Change city</button></div>}
        <div className="weather-setup-fields">
          <DestinationAutocomplete label="Departure city" value={originText} selectedLocation={draft.origin} required={draft.mode === "driving"} allowCustom={false} placeholder="Where are you leaving from?"
            onChange={(text, location) => { setOriginText(text); updateDraft("origin", location); }} />
          {changingDestination && <DestinationAutocomplete label="Destination city" value={destinationText} selectedLocation={draft.destination} allowCustom={false} placeholder="Which city will you stay in?"
            onChange={(text, location) => { setDestinationText(text); updateDraft("destination", location); }} />}
        </div>
        {draft.mode === "flight" && <p className="weather-muted">Departure city is optional. You can start with just your destination’s weather.</p>}
        {invalidOrigin && <p className="weather-field-error">Choose a departure city from the suggestions, or clear the field to skip it when flying.</p>}
        <details className="weather-time-options" open={draft.mode === "driving" ? true : undefined} key={draft.mode}>
          <summary>{draft.mode === "driving" ? "When will you set off?" : "Add departure times (optional)"}</summary>
          <p className="weather-muted">{draft.mode === "driving" ? "We’ll use 9 a.m. local time unless you change it. This helps us check weather as you drive." : "Leave these blank for a full-day outlook. Add times if you know them."}</p>
          <div className="weather-time-fields"><label>Leaving on {formatDay(trip.start_date)}<input type="time" disabled={!draft.origin} value={draft.outbound_time || ""} onChange={(e) => updateDraft("outbound_time", e.target.value)} /><small>{draft.origin ? `${shortCity(draft.origin)} local time` : "Add a departure city to set this time"}</small></label>
            <label>Returning on {formatDay(trip.end_date)}<input type="time" disabled={!draft.destination} value={draft.return_time || ""} onChange={(e) => updateDraft("return_time", e.target.value)} /><small>{draft.destination ? `${shortCity(draft.destination)} local time` : "Choose a destination city to set this time"}</small></label></div>
        </details>
        <div className="weather-form-actions"><button className="weather-primary" disabled={busy || !draftReady}>{busy ? "Saving…" : waiting ? "Save trip details" : "Show my forecast"}</button>{plan && <button type="button" className="weather-text-button" disabled={busy} onClick={() => { setEditing(false); setError(""); }}>Cancel</button>}</div>
      </form>}

      {!editing && <>
      {result?.monitoring_complete ? <section className="weather-waiting"><div><h2>This trip has ended</h2><p>Automatic weather checks have finished. Your saved weather updates are below.</p></div></section>
        : waiting ? <section className="weather-waiting"><div>
          <span className="weather-eyebrow">Forecast window</span><h2>Forecasts start around {opening.toLocaleDateString("en-US", { month: "long", day: "numeric" })}</h2>
          <p>Weather forecasts cover about the next two weeks. Your {formatDay(trip.start_date)} trip is a little further out.</p>
          <p>{plan?.destination ? "Automatic checks are scheduled. Come back closer to departure for your forecast and weather updates." : "Choose your destination city above so we can check its weather as your trip approaches."}</p>
        </div><div className="weather-opening-date" aria-hidden="true"><span>{opening.toLocaleDateString("en-US", { month: "short" })}</span><strong>{opening.getDate()}</strong><small>Forecasts begin</small></div></section>
        : outlook.knownHours ? <section className={`weather-lead weather-lead-${outlook.severity === "low" && !outlook.complete ? "unknown" : outlook.severity}`}>
          <div>
            <span className="weather-eyebrow">{result?.status === "stale" ? "Last saved forecast" : plan?.origin ? "Travel outlook" : "Destination outlook"}</span><h2>{advice.title}</h2>
            {outlook.concern && <p className="weather-concern-place">{shortCity(outlook.concern.location)} · {formatMoment(outlook.concern.time, outlook.concern.location.timezone)}</p>}
            <p>{advice.advice}</p>{!outlook.complete && <p className="weather-muted">Some hours or measurements are still unavailable. This summary covers the forecasts we have.</p>}
          </div><TemperatureChart rows={groups.find((group) => group.key === "stay")?.summary.rows || []} location={plan?.destination} />
        </section> : !editing && <section className="weather-waiting" role="status"><div><h2>{busy || result?.refreshing ? "Checking your weather…" : "Your forecast isn’t ready yet"}</h2><p>{busy || result?.refreshing ? "You can leave this page. Your forecast will be here when the check finishes." : "We’ll check again automatically. You can also try an update below."}</p></div></section>}

      {!editing && plan?.destination && !plan.origin && !result?.monitoring_complete && <div className="weather-add-origin"><div><strong>Want weather for the journey too?</strong><p>Add your departure city to check both ends of your trip{plan.mode === "driving" ? " and your road route" : ""}.</p></div><button className="weather-secondary" type="button" disabled={busy || result?.refreshing} onClick={() => startEditing()}>Add departure city</button></div>}

      {!waiting && !result?.monitoring_complete && <>
        {(result?.status === "stale" || result?.last_error) && <p className="weather-note" role="status">We couldn’t get a complete update. {outlook.knownHours ? "The last saved forecast is shown below; conditions may have changed." : "We’ll try again automatically."}</p>}
        {!!highlighted.length && <section className="weather-updates"><h2>What’s changed <span>{unread.length} new</span></h2>{highlighted.map((event) => <WeatherUpdate key={event.id} event={event} onRead={markRead} />)}</section>}
        {!!groups.length && <section className="weather-journey-section"><div className="weather-section-heading"><h2>Your forecast</h2><span>Details for each part of your trip</span></div><div className="weather-journey-grid">{groups.map((group) => <JourneyCard key={group.key} group={group} forecast={forecast} plan={plan || emptyPlan} />)}</div></section>}
        <div className="weather-update-bar"><span>{busy || result?.refreshing ? "Updating your weather…" : forecast?.retrieved_at && outlook.knownHours ? `Updated ${formatMoment(forecast.retrieved_at)}` : "Automatic weather checks are scheduled"}</span>
          <button type="button" className="weather-text-button" disabled={busy || !result?.next_refresh_at || result?.refreshing} onClick={() => checkForecast()}>{busy || result?.refreshing ? "Updating…" : "Update now"}</button></div>
      </>}
      {!!older.length && <details className="weather-past-updates"><summary>{highlighted.length ? "All other weather updates" : "Past weather updates"} ({older.length})</summary>{older.map((event) => <WeatherUpdate key={event.id} event={event} onRead={markRead} />)}</details>}
      {!events.length && !editing && <p className="weather-quiet-status">Significant weather changes will appear here as your trip approaches.</p>}
      </>}
      {!editing && <details className="weather-about"><summary>About these forecasts</summary><p>Forecasts are checked every six hours, and hourly within 72 hours of your next travel day. Flight outlooks use city weather; check your airline for confirmed flight status. Weather advisories describe possible travel impacts, not confirmed delays.</p>
        {forecast?.model?.status === "available" && <p>{forecast.model.label}: {Math.round(forecast.model.probability * 100)}%. {forecast.model.scope}</p>}
        <p>Forecasts: <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a> · Locations: <a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a> · Routes: <a href="https://project-osrm.org/" target="_blank" rel="noreferrer">OSRM</a> / <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>.</p>
      </details>}
    </>}
  </section>;
}
