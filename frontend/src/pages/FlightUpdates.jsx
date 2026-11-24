import { useState } from "react";
import { getAirports, getFlights } from "../api";
import "../flight-updates.css";

//Two ways this page is used:
//  Top menu "Flight Updates": general flight status and airport search, not tied to a trip.
//  A trip's "Airport Data" button: only="airports" shows just the airport search.
//This page shows a flight's CURRENT information only. Alerts and the history of changes live on a trip's Flight Plan page.

function AirportLabel({ airport }) {
  if (!airport) return "Unknown airport";
  return `${airport.name || "Unknown airport"} (${airport.iata_code || airport.icao_code || "?"})${airport.city ? ` · ${airport.city}` : ""}`;
}

//Google Maps link for an airport. Searching by name and code opens the airport's own listing (address, directions),
//and falls back to the coordinates if there's no name. No API key or request is needed
function mapsLink(airport) {
  const query = airport.name ? `${airport.name} (${airport.iata_code})` : `${airport.latitude},${airport.longitude}`;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function TimeLines({ side }) {
  const late = side.delay_minutes;
  return (
    <>
      <small>Scheduled: {side.scheduled || "Unavailable"}</small>
      {side.estimated && side.estimated !== side.scheduled && <small>Expected now: {side.estimated}</small>}
      {late > 0 && <small className="aero-flight-late">Running {late} min late</small>}
      {side.terminal && <small>Terminal: {side.terminal}</small>}
      {side.gate && <small>Gate: {side.gate}</small>}
    </>
  );
}

function FlightCard({ flight }) {
  const dep = flight.departure || {};
  const arr = flight.arrival || {};
  return (
    <article className="aero-flight-card">
      <div className="aero-flight-heading">
        <strong>{flight.flight_iata || flight.flight_icao || "Flight"}</strong>
        <span className={`aero-flight-status ${flight.status === "cancelled" ? "cancelled" : ""}`}>
          {(flight.status || "unknown").replace("-", " ")}
        </span>
      </div>
      <div className="aero-flight-route">
        <div><small>Departure</small><p><AirportLabel airport={dep.airport} /></p><TimeLines side={dep} /></div>
        <span className="aero-flight-arrow" aria-hidden="true">→</span>
        <div><small>Arrival</small><p><AirportLabel airport={arr.airport} /></p><TimeLines side={arr} /></div>
      </div>
      {flight.updated && <p className="aero-flight-updated">Last updated: {flight.updated}</p>}
    </article>
  );
}

export default function FlightUpdates({ initialTab = "flights", only = null, onBack }) {
  const [tab, setTab] = useState(only || initialTab);
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

  const airportsOnly = only === "airports";

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
        <p className="aero-flight-eyebrow">{airportsOnly ? "Trip Tools" : "AeroLink Travel Updates"}</p>
        <h1>{airportsOnly ? "Airport Data" : "Flight & Airport Lookup"}</h1>
        {airportsOnly ? (
          <p>Search any airport by name, city, or code to see where it is and its IATA and ICAO codes.</p>
        ) : (
          <p>Check a flight's current status or find an airport. This shows a flight's latest information, including a new time if it's running late, but it doesn't keep a history of what changed or send alerts. For alerts and an update history, add the flight to a trip's Flight Plan.</p>
        )}
      </header>

      {!airportsOnly && (
        <div className="aero-flight-tabs" role="group" aria-label="Search mode">
          <button type="button" className={tab === "flights" ? "selected" : ""} onClick={() => setTab("flights")}>Flight status</button>
          <button type="button" className={tab === "airports" ? "selected" : ""} onClick={() => setTab("airports")}>Airport search</button>
        </div>
      )}

      {tab === "flights" && !airportsOnly ? (
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
          <p className="aero-flight-hint">Results show the latest known information at the moment you search. With live data on, searches use the AirLabs allowance and are saved for 5 minutes; nothing is checked automatically.</p>
          {flightError && <p className="aero-flight-error" role="alert">{flightError}</p>}
          {flightData && (
            <div className="aero-flight-results">
              <h2>{flightData.count} flight{flightData.count === 1 ? "" : "s"} found</h2>
              {flightData.live === false ? (
                <p className="aero-flight-notice" role="status">Live data is off, so these results come from flights saved in AeroLink (test data), not AirLabs.</p>
              ) : (
                <p className="aero-flight-hint">Source: AirLabs ({flightData.source}) · {flightData.cached ? "Saved result from the last 5 minutes" : "Latest request"}</p>
              )}
              {flightData.flights.map((flight, index) => <FlightCard key={`${flight.flight_iata || flight.flight_icao}-${flight.flight_date || ""}-${index}`} flight={flight} />)}
              {flightData.count === 0 && <p>No matching flights were found. Try another flight number or a different airport.</p>}
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
          <p className="aero-flight-hint">Airport searches use AeroLink's saved airport list and never use AirLabs requests.</p>
          {airportError && <p className="aero-flight-error" role="alert">{airportError}</p>}
          {airports && <div className="aero-flight-results"><h2>{airports.length} airport{airports.length === 1 ? "" : "s"} found</h2>
            {airports.map((airport) => <article className="aero-airport-card" key={airport.iata_code}>
              <strong>{airport.name}</strong><span>{airport.iata_code} / {airport.icao_code || "—"}</span>
              <small>{airport.city || "Unknown city"}, {airport.country}</small>
              <small>Coordinates: {airport.latitude}, {airport.longitude}</small>
              <a className="aero-airport-map" href={mapsLink(airport)} target="_blank" rel="noopener noreferrer">Open in Maps ↗</a>
            </article>)}
          </div>}
        </>
      )}
    </section>
  );
}
