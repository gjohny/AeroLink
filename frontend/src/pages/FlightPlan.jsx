import {useCallback, useEffect, useState} from "react";
import "../trips.css";
import "../flightplan.css";

const POLL_MS = 30000;

const emptyForm = {flight_number: "", flight_date: "", departure_airport: "", arrival_airport: ""};

//Same labels and color families as the alert bell
const TYPE_LABELS = {delay: "Delay", arrival_delay: "Arrival delay", gate_change: "Gate change", arrival_gate_change: "Arrival gate", cancellation: "Cancelled"};

const STATUS_LABELS = {scheduled: "On time", delayed: "Delayed", cancelled: "Cancelled", boarding: "Boarding", departed: "Departed", active: "In the air", en_route: "In the air", landed: "Landed", diverted: "Diverted"};

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "Something went wrong.");
  return result;
}

function formatDay(value) {
  return value ? new Date(`${value}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "";
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} min ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} hr ago`;
  }
  return new Date(iso).toLocaleDateString();
}

function PlaneIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 3 9 15" />
      <path d="m21 3-7 18-4-8-8-4 19-6Z" />
    </svg>
  );
}

//A value that may have changed: old value crossed out, new value in the change's color
function Changed({ value, change, format = (v) => v }) {
  if (!change) {
    return <span>{value ? format(value) : "—"}</span>;
  }
  return (
    <span className={`fp-changed fp-type-${change.type}`}>
      <s aria-label={`was ${format(change.old)}`}>{format(change.old)}</s>
      <strong>{format(change.new)}</strong>
    </span>
  );
}

function AirportEnd({ side, label, data, timeChange, gateChange }) {
  const place = [data.name, data.city].filter(Boolean).join(", ");
  return (
    <div className={`fp-end fp-end-${side}`}>
      <span className="fp-code">{data.code || "???"}</span>
      <span className="fp-place">{place || (data.code ? "Airport details unavailable" : "Airport not set")}</span>
      <dl className="fp-details">
        <div>
          <dt>{label}</dt>
          <dd><Changed value={data.estimated || data.scheduled} change={timeChange} format={formatTime} /></dd>
        </div>
        <div>
          <dt>Terminal</dt>
          <dd>{data.terminal || "—"}</dd>
        </div>
        <div>
          <dt>Gate</dt>
          <dd><Changed value={data.gate} change={gateChange} /></dd>
        </div>
      </dl>
    </div>
  );
}

function FlightCard({ flight, isOwner, onSwap, onRemove }) {
  const cancelled = flight.status === "cancelled";
  const delayed = !cancelled && (flight.changes.departure_time || flight.changes.arrival_time);
  let statusKey = "waiting";
  let statusText = "Awaiting live data";

  if (flight.has_live_data) {
    statusKey = cancelled ? "cancelled" : delayed ? "delayed" : flight.status === "scheduled" ? "ontime" : "info";
    statusText = delayed && flight.status === "scheduled" ? "Delayed" : STATUS_LABELS[flight.status] || flight.status;
  }

  const unread = flight.alerts.filter((alert) => !alert.is_read).length;

  return (
    <article className={`fp-card${cancelled ? " fp-card-cancelled" : ""}`} aria-label={`Flight ${flight.flight_number}`}>
      <header className="fp-card-top">
        <div>
          <h2 className="fp-number">{flight.flight_number}</h2>
          <p className="fp-sub">{[flight.airline, formatDay(flight.flight_date)].filter(Boolean).join(" · ")}</p>
        </div>
        <span className={`fp-status fp-status-${statusKey}`}>{statusText}</span>
      </header>

      {cancelled && <p className="fp-cancel-banner" role="status">This flight was cancelled. Swap it for your new flight to keep getting updates.</p>}

      <div className="fp-route">
        <AirportEnd side="depart" label="Departs" data={flight.departure} timeChange={flight.changes.departure_time} gateChange={flight.changes.departure_gate} />
        <div className="fp-path" aria-hidden="true"><span /><PlaneIcon /><span /></div>
        <AirportEnd side="arrive" label="Arrives" data={flight.arrival} timeChange={flight.changes.arrival_time} gateChange={flight.changes.arrival_gate} />
      </div>

      {!flight.has_live_data && <p className="fp-waiting">No live updates for this flight yet. Times, gates, and status will show here as soon as flight data comes in.</p>}

      <footer className="fp-card-footer">
        <span className="fp-updated">{flight.last_updated ? `Updated ${timeAgo(flight.last_updated)}` : ""}</span>
        {isOwner && (
          <div className="fp-card-actions">
            <button type="button" className="trips-share" onClick={() => onSwap(flight)}>Swap Flight</button>
            <button type="button" className="trips-delete fp-remove" onClick={() => onRemove(flight)}>Remove</button>
          </div>
        )}
      </footer>

      {flight.alerts.length > 0 && (
        <details className="fp-history">
          <summary>
            Update history ({flight.alerts.length})
            {unread > 0 && <span className="fp-new-count">{unread} new</span>}
          </summary>
          <ul>
            {flight.alerts.map((alert) => (
              <li key={alert.id} className={alert.is_read ? "" : "fp-history-unread"}>
                <span className={`fp-chip fp-type-${alert.alert_type}`}>{TYPE_LABELS[alert.alert_type] || "Update"}</span>
                <span className="fp-history-text">
                  <strong>{alert.message}</strong>
                  {alert.detail && <small>{alert.detail}</small>}
                </span>
                <time className="fp-history-time" dateTime={alert.created_at}>{timeAgo(alert.created_at)}</time>
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

export default function FlightPlan({ tripId, onNavigate }) {
  const [trip, setTrip] = useState(null);
  const [flights, setFlights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  //null = form closed, "new" = adding, or the flight being swapped
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await api(`/api/trips/${tripId}/flights`);
      setTrip(result.trip);
      setFlights(result.flights);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  //Load on open, then check for updates every 30 seconds like the bell does
  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  //Escape closes the confirmation dialog
  useEffect(() => {
    if (!confirming) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape" && !confirmBusy) setConfirming(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [confirming, confirmBusy]);

  function openAdd() {
    setEditing("new");
    setForm({ ...emptyForm, flight_date: trip?.start_date || "" });
    setFormError("");
  }

  function openSwap(flight) {
    setEditing(flight);
    setForm({ flight_number: "", flight_date: flight.flight_date, departure_airport: flight.entered.departure_airport || "", arrival_airport: flight.entered.arrival_airport || "" });
    setFormError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeForm() {
    setEditing(null);
    setFormError("");
  }

  async function saveFlight(event) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const swapping = editing && editing !== "new";
    try {
      const url = swapping ? `/api/trips/${tripId}/flights/${editing.id}` : `/api/trips/${tripId}/flights`;
      await api(url, { method: swapping ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      closeForm();
      await load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function removeFlight(flight) {
    setConfirming({
      title: `Remove ${flight.flight_number}?`,
      message: `This takes ${flight.flight_number} on ${formatDay(flight.flight_date)} off this trip, along with its updates. Everyone on the trip will stop getting alerts for it.`,
      onConfirm: async () => {
        try {
          await api(`/api/trips/${tripId}/flights/${flight.id}`, { method: "DELETE" });
          await load();
        } catch (err) {
          setError(err.message);
        }
      },
    });
  }

  async function runConfirm() {
    setConfirmBusy(true);
    try {
      await confirming.onConfirm();
    } finally {
      setConfirmBusy(false);
      setConfirming(null);
    }
  }

  const isOwner = Boolean(trip?.is_owner);
  const swapping = editing && editing !== "new";

  return (
    <section className="trips-page fp-page">
      <header className="trips-hero">
        <div>
          <span className="trips-eyebrow">✈ FLIGHT PLAN</span>
          <h1>{trip ? trip.destination : "Flight Plan"}</h1>
          <p>{trip ? `${formatDay(trip.start_date)} – ${formatDay(trip.end_date)}` : "Your flights, live status, and updates"}</p>
        </div>
        <div className="trips-hero-actions">
          {isOwner && !editing && <button type="button" className="trips-secondary" onClick={openAdd}>+ Add Flight</button>}
          <button type="button" className="trips-primary" onClick={() => onNavigate(`/trips/${tripId}`)}>← Back to Trip</button>
        </div>
      </header>

      {error && <p className="fp-error" role="alert">{error}</p>}

      {editing && (
        <form className="trips-create fp-form" onSubmit={saveFlight}>
          <h2>{swapping ? `Swap ${editing.flight_number}` : "Add a Flight"}</h2>
          <p>{swapping ? `Enter the flight that replaces ${editing.flight_number}. Its old updates will be cleared from this trip.` : "Enter the flight number and departure date. Airports are optional and fill in on their own once live data arrives."}</p>
          <div className="trips-form-grid fp-form-grid">
            <label>Flight number<input required autoFocus placeholder="e.g. AA100" value={form.flight_number} onChange={(e) => setForm({ ...form, flight_number: e.target.value.toUpperCase() })} /></label>
            <label>Departure date<input required type="date" value={form.flight_date} onChange={(e) => setForm({ ...form, flight_date: e.target.value })} /></label>
            <label>From <small>(optional)</small><input maxLength={3} placeholder="e.g. ORD" value={form.departure_airport} onChange={(e) => setForm({ ...form, departure_airport: e.target.value.toUpperCase() })} /></label>
            <label>To <small>(optional)</small><input maxLength={3} placeholder="e.g. FCO" value={form.arrival_airport} onChange={(e) => setForm({ ...form, arrival_airport: e.target.value.toUpperCase() })} /></label>
          </div>
          {formError && <p className="fp-form-error" role="alert">{formError}</p>}
          <div className="fp-form-actions">
            <button type="button" className="trips-secondary" onClick={closeForm}>Cancel</button>
            <button type="submit" className="trips-primary" disabled={saving}>{saving ? "Saving..." : swapping ? "Swap Flight →" : "Add Flight →"}</button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="fp-empty">Loading flights...</p>
      ) : trip && flights.length === 0 && !editing ? (
        <div className="trips-empty fp-empty-card">
          <span className="fp-empty-icon"><PlaneIcon /></span>
          <h2>No flights yet</h2>
          <p>{isOwner ? "Add your flights to see their status, gates, and any delays or cancellations in one place." : `${trip.owner_name || "The trip owner"} hasn't added any flights to this trip yet.`}</p>
          {isOwner && <button type="button" className="trips-primary" onClick={openAdd}>+ Add Your First Flight</button>}
        </div>
      ) : (
        <>
          {flights.length > 0 && <p className="fp-note">Times are shown in your time zone.{!isOwner && trip ? ` Only ${trip.owner_name || "the trip owner"} can change these flights.` : ""}</p>}
          <div className="fp-list">
            {flights.map((flight) => (
              <FlightCard key={flight.id} flight={flight} isOwner={isOwner} onSwap={openSwap} onRemove={removeFlight} />
            ))}
          </div>
        </>
      )}

      {confirming && (
        <div className="trips-editor-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget && !confirmBusy) setConfirming(null); }}>
          <section className="trips-editor-dialog trips-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="fp-confirm-title" aria-describedby="fp-confirm-message">
            <div className="trips-editor-header">
              <div><span className="trips-editor-eyebrow">REMOVE FLIGHT</span><h2 id="fp-confirm-title">{confirming.title}</h2></div>
              <button type="button" className="trips-editor-close" onClick={() => setConfirming(null)} disabled={confirmBusy} aria-label="Close dialog">×</button>
            </div>
            <p id="fp-confirm-message" className="trips-confirm-message">{confirming.message}</p>
            <div className="trips-editor-footer trips-confirm-footer">
              <button type="button" className="trips-secondary" autoFocus onClick={() => setConfirming(null)} disabled={confirmBusy}>Cancel</button>
              <button type="button" className="trips-danger" onClick={runConfirm} disabled={confirmBusy}>{confirmBusy ? "Working..." : "Remove"}</button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}