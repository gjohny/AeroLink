import { useState } from "react";
import { getAirports, getFlights } from "../api";
import "../flight-updates.css";

function AirportLabel({ airport }) {
  if (!airport) return "Unknown airport";
  return `${airport.name || "Unknown airport"} (${airport.iata_code || airport.icao_code || "?"})${airport.city ? ` · ${airport.city}` : ""}`;
}

function FlightCard({ flight }) {
  const alerts = flight.alerts || [];
  const dep = flight.departure || {};
  const arr = flight.arrival || {};
  return (
    <article className="aero-flight-card">
      <div className="aero-flight-heading">
        <strong>{flight.flight_iata || flight.flight_icao || "Flight"}</strong>
        <span className={`aero-flight-status ${flight.status === "cancelled" ? "cancelled" : ""}`}>
          {flight.status || "unknown"}
        </span>
      </div>
      <div className="aero-flight-route">
        <div><small>Departure</small><p><AirportLabel airport={dep.airport} /></p>
          <small>Scheduled: {dep.scheduled || "Unavailable"}</small>
          {dep.estimated && <small>Estimated: {dep.estimated}</small>}
          {dep.gate && <small>Gate: {dep.gate}</small>}
        </div>
        <span className="aero-flight-arrow" aria-hidden="true">→</span>
        <div><small>Arrival</small><p><AirportLabel airport={arr.airport} /></p>
          <small>Scheduled: {arr.scheduled || "Unavailable"}</small>
          {arr.estimated && <small>Estimated: {arr.estimated}</small>}
          {arr.gate && <small>Gate: {arr.gate}</small>}
        </div>
      </div>
      {alerts.length > 0 ? (
        <div className="aero-flight-alerts">
          {alerts.map((alert, index) => (
            <p role="status" className={alert.type === "cancelled" ? "aero-flight-danger" : "aero-flight-warning"} key={`${alert.type}-${index}`}>
              {alert.type === "cancelled" ? "⚠" : "⏱"} {alert.message}
            </p>
          ))}
        </div>
      ) : <p className="aero-flight-no-alert">No confirmed delay or cancellation alert from available data.</p>}
    </article>
  );
}

export default function FlightUpdates({ initialTab = "flights", onBack }) {
  const [tab, setTab] = useState(initialTab);
  const [flightInput, setFlightInput] = useState("");
  const [departureInput, setDepartureInput] = useState("");
  const [arrivalInput, setArrivalInput] = useState("");
  const [mode, setMode] = useState("auto");
  const [flightData, setFlightData] = useState(null);
  const [flightError, setFlightError] = useState("");
  const [loadingFlights, setLoadingFlights] = useState(false);
  const [airportSearch, setAirportSearch] = useState("");
  const [airports, setAirports] = useState(null);
  const [airportError, setAirportError] = useState("");
  const [loadingAirports, setLoadingAirports] = useState(false);

  async function searchFlights(event) {
    event.preventDefault();
    setFlightError("");
    setFlightData(null);
    const flight_iata = flightInput.trim().toUpperCase();
    const dep_iata = departureInput.trim().toUpperCase();
    const arr_iata = arrivalInput.trim().toUpperCase();
    if (!flight_iata && !dep_iata && !arr_iata) {
      setFlightError("Enter a flight number or at least one airport code.");
      return;
    }
    setLoadingFlights(true);
    try {
      const result = await getFlights({ flight_iata, dep_iata, arr_iata, mode, limit: 30 });
      setFlightData(result);
    } catch (error) {
      setFlightError(error.message);
    } finally {
      setLoadingFlights(false);
    }
  }

  async function searchAirports(event) {
    event.preventDefault();
    setAirportError("");
    setAirports(null);
    if (!airportSearch.trim()) {
      setAirportError("Enter an airport name, city, or code.");
      return;
    }
    setLoadingAirports(true);
    try {
      const result = await getAirports({ q: airportSearch.trim(), limit: 20 });
      setAirports(result.airports);
    } catch (error) {
      setAirportError(error.message);
    } finally {
      setLoadingAirports(false);
    }
  }

  return (
    <section className="aero-flight-page">
      <header className="aero-flight-intro">
        {onBack && <button type="button" className="aero-flight-back" onClick={onBack}>← Back to Trip</button>}
        <p className="aero-flight-eyebrow">AeroLink Travel Updates</p>
        <h1>Flights & Airports</h1>
        <p>Look up flight status, delay alerts, and airport information. Flight data is provided by AirLabs and may not cover every flight.</p>
      </header>
      <div className="aero-flight-tabs" role="group" aria-label="Search mode">
        <button type="button" className={tab === "flights" ? "selected" : ""} onClick={() => setTab("flights")}>Flight status</button>
        <button type="button" className={tab === "airports" ? "selected" : ""} onClick={() => setTab("airports")}>Airport search</button>
      </div>
      {tab === "flights" ? (
        <>
          <form className="aero-flight-form" onSubmit={searchFlights}>
            <label>Flight number (e.g. AA100)
              <input maxLength="10" value={flightInput} onChange={(event) => setFlightInput(event.target.value)} placeholder="AA100" />
            </label>
            <label>Departing from (IATA)
              <input maxLength="3" value={departureInput} onChange={(event) => setDepartureInput(event.target.value)} placeholder="DFW" />
            </label>
            <label>Arriving at (IATA)
              <input maxLength="3" value={arrivalInput} onChange={(event) => setArrivalInput(event.target.value)} placeholder="LAX" />
            </label>
            <label>Data type
              <select value={mode} onChange={(event) => setMode(event.target.value)}>
                <option value="auto">Automatic (recommended)</option>
                <option value="schedules">Schedules and delays</option>
                <option value="live">Live aircraft</option>
              </select>
            </label>
            <button type="submit" disabled={loadingFlights}>{loadingFlights ? "Looking up…" : "Find flights"}</button>
          </form>
          <p className="aero-flight-hint">Automatic uses detailed flight info for a flight number or airport schedules when searching by airport. Requests are cached for 5 minutes to save your API quota. No automatic polling.</p>
          {flightError && <p className="aero-flight-error" role="alert">{flightError}</p>}
          {flightData && (
            <div className="aero-flight-results">
              <h2>{flightData.count} flight{flightData.count === 1 ? "" : "s"} found</h2>
              <p className="aero-flight-hint">Source: {flightData.source} · {flightData.cached ? "Cached response" : "Latest request"} · Alerts at {flightData.delay_threshold_minutes}+ minutes</p>
              {flightData.flights.map((flight, index) => <FlightCard key={`${flight.flight_iata || flight.flight_icao}-${index}`} flight={flight} />)}
              {flightData.count === 0 && <p>No matching flights were returned. Try another flight number or a different airport.</p>}
            </div>
          )}
        </>
      ) : (
        <>
          <form className="aero-flight-form" onSubmit={searchAirports}>
            <label className="aero-flight-wide">Airport name, city, IATA or ICAO code
              <input value={airportSearch} maxLength="100" onChange={(event) => setAirportSearch(event.target.value)} placeholder="College Station, CLL, or DFW" />
            </label>
            <button type="submit" disabled={loadingAirports}>{loadingAirports ? "Searching…" : "Find airports"}</button>
          </form>
          <p className="aero-flight-hint">Airport searches use local SQLite data and do not consume AirLabs API requests.</p>
          {airportError && <p className="aero-flight-error" role="alert">{airportError}</p>}
          {airports && <div className="aero-flight-results"><h2>{airports.length} airport{airports.length === 1 ? "" : "s"} found</h2>
            {airports.map((airport) => <article className="aero-airport-card" key={airport.iata_code}>
              <strong>{airport.name}</strong><span>{airport.iata_code} / {airport.icao_code || "—"}</span>
              <small>{airport.city || "Unknown city"}, {airport.country}</small>
              <small>Coordinates: {airport.latitude}, {airport.longitude}</small>
            </article>)}
          </div>}
        </>
      )}
    </section>
  );
}
