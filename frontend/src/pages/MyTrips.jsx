import { useEffect, useState } from "react";
import "../trips.css";
import { PREFERENCE_GROUPS } from "../data/preferenceOptions";

const CATEGORIES = PREFERENCE_GROUPS.map(({ key, label }) => [key, label]);
const FALLBACK = "/images/aerolink-home-image.jpeg";
const emptyForm = { destination: "", start_date: "", end_date: "", budget: "", travelers: 1, use_saved_preferences: true };
const formatDate = (value) => value ? new Date(`${value}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "Something went wrong.");
  return result;
}

function TripIcon({ name, size = 21 }) {
  const paths = {
    heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18M8 14h2M14 14h2M8 18h2" /></>,
    wallet: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 9h18M15 13h7v5h-7a2.5 2.5 0 0 1 0-5Z" /><path d="M17 15.5h.01" /></>,
    plane: <><path d="M21 3 9 15" /><path d="m21 3-7 18-4-8-8-4 19-6Z" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
    airport: <><circle cx="12" cy="12" r="8" /><path d="M12 2v20M2 12h20" /><circle cx="12" cy="12" r="2" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export default function MyTrips({ onNavigate, selectedTripId = null }) {
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [savedPreferences, setSavedPreferences] = useState({});
  const [customPreferences, setCustomPreferences] = useState({});
  const [editingCategory, setEditingCategory] = useState(null);
  const [editorBackup, setEditorBackup] = useState(null);
  const [preferenceSearch, setPreferenceSearch] = useState("");
  const [customEntry, setCustomEntry] = useState("");
  const [editorError, setEditorError] = useState("");

  //Trip sharing
  const [joining, setJoining] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [joinSaving, setJoinSaving] = useState(false);
  const [shareCode, setShareCode] = useState("");
  const [copied, setCopied] = useState(false);
  // In-app confirmation dialog: { eyebrow, title, message, confirmLabel, onConfirm }
  const [confirming, setConfirming] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    Promise.all([api("/api/trips"), api("/api/preferences")])
      .then(([tripData, prefData]) => {
        if (!mounted) return;
        setTrips(tripData.trips || []);
        const prefs = Object.fromEntries(CATEGORIES.map(([key]) => [key, prefData.preferences?.[key] || []]));
        setSavedPreferences(prefs);
        setCustomPreferences(prefs);
      })
      .catch((err) => { if (mounted) setError(err.message); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  const selectedTrip = selectedTripId ? trips.find((trip) => trip.id === Number(selectedTripId)) : null;

  //Hide the last trip's share code when a different trip is opened
  useEffect(() => {
    setShareCode("");
    setCopied(false);
  }, [selectedTripId]);

  // Escape closes the confirmation dialog
  useEffect(() => {
    if (!confirming) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape" && !confirmBusy) setConfirming(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [confirming, confirmBusy]);
  const update = (key, value) => setForm((old) => ({ ...old, [key]: value }));

  function openEditor(key) {
    setEditorBackup(Object.fromEntries(CATEGORIES.map(([field]) => [field, [...(customPreferences[field] || [])]])));
    setEditingCategory(key);
    setPreferenceSearch("");
    setCustomEntry("");
    setEditorError("");
  }

  function closeEditor(save) {
    if (!save && editorBackup) setCustomPreferences(editorBackup);
    setEditingCategory(null);
    setEditorBackup(null);
    setPreferenceSearch("");
    setCustomEntry("");
    setEditorError("");
  }

  function togglePreference(key, option) {
    const current = customPreferences[key] || [];
    if (!current.includes(option) && current.length >= 50) {
      setEditorError("You can select up to 50 preferences in this category.");
      return;
    }
    setEditorError("");
    setCustomPreferences((old) => ({
      ...old,
      [key]: (old[key] || []).includes(option)
        ? old[key].filter((value) => value !== option)
        : [...(old[key] || []), option],
    }));
  }

  function addCustomPreference(event) {
    event.preventDefault();
    const value = customEntry.trim().replace(/\s+/g, " ");
    if (!value || !editingCategory) return;
    if (value.length > 100) {
      setEditorError("Custom preferences must be 100 characters or fewer.");
      return;
    }
    const group = PREFERENCE_GROUPS.find((item) => item.key === editingCategory);
    const all = [...group.options, ...(customPreferences[editingCategory] || [])];
    const existing = all.find((item) => item.toLowerCase() === value.toLowerCase());
    if (existing) {
      if (!(customPreferences[editingCategory] || []).includes(existing)) togglePreference(editingCategory, existing);
    } else {
      togglePreference(editingCategory, value);
    }
    setCustomEntry("");
  }

  async function createTrip(event) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      const payload = {
        ...form,
        travelers: Number(form.travelers),
        budget: form.budget === "" ? null : Number(form.budget),
        preferences: customPreferences,
      };
      const result = await api("/api/trips", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setTrips((old) => [result.trip, ...old]);
      setCreating(false);
      setForm(emptyForm);
      onNavigate(`/trips/${result.trip.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function photoCredit(trip) {
    const credit = trip.image_credit;
    if (!trip.image_url || !credit?.photographer_url || !credit?.unsplash_url) return null;
    return <span className="trips-photo-credit" onClick={(event) => event.stopPropagation()}>
      Photo by <a href={credit.photographer_url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()}>{credit.photographer}</a> on <a href={credit.unsplash_url} target="_blank" rel="noopener noreferrer" onClick={(event) => event.stopPropagation()}>Unsplash</a>
    </span>;
  }

  async function shareTrip(trip) {
    setError("");
    try {
      const result = await api(`/api/trips/${trip.id}/share`, { method: "POST" });
      setShareCode(result.code);
      setCopied(false);
    } catch (err) {
      setError(err.message);
    }
  }

  async function copyShareCode() {
    try {
      await navigator.clipboard.writeText(shareCode);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function joinTrip(event) {
    event.preventDefault();
    setError("");
    setJoinSaving(true);
    try {
      const result = await api("/api/trips/join", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: joinCode }) });
      setTrips((old) => [result.trip, ...old]);
      setJoining(false);
      setJoinCode("");
      onNavigate(`/trips/${result.trip.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setJoinSaving(false);
    }
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

  // Put an updated trip from the server back into the list
  function replaceTrip(updated) {
    setTrips((old) => old.map((item) => (item.id === updated.id ? updated : item)));
  }

  function leaveTrip(trip) {
    setConfirming({
      eyebrow: "LEAVE TRIP",
      title: `Leave ${trip.destination}?`,
      message: `This trip will be removed from your trips. You will need a new code from ${trip.owner_name || "the owner"} to rejoin.`,
      confirmLabel: "Leave Trip",
      onConfirm: async () => {
        try {
          await api(`/api/trips/${trip.id}/leave`, { method: "POST" });
          setTrips((old) => old.filter((item) => item.id !== trip.id));
          onNavigate("/trips");
        } catch (err) {
          setError(err.message);
        }
      },
    });
  }

  function deleteTrip(trip) {
    const sharedNote = trip.shared_with?.length ? " It will also be removed for everyone you shared it with." : "";
    setConfirming({
      eyebrow: "DELETE TRIP",
      title: `Delete ${trip.destination}?`,
      message: `This permanently deletes the trip.${sharedNote} This cannot be undone.`,
      confirmLabel: "Delete Trip",
      onConfirm: async () => {
        try {
          await api(`/api/trips/${trip.id}`, { method: "DELETE" });
          setTrips((old) => old.filter((item) => item.id !== trip.id));
          onNavigate("/trips");
        } catch (err) {
          setError(err.message);
        }
      },
    });
  }

  function removeMember(trip, member) {
    setConfirming({
      eyebrow: "STOP SHARING",
      title: `Remove ${member.name}?`,
      message: `${member.name} will no longer see this trip. Your current share code will stop working, so share again to get a new code for anyone else you want to invite.`,
      confirmLabel: "Remove",
      onConfirm: async () => {
        try {
          const result = await api(`/api/trips/${trip.id}/members/${member.id}`, { method: "DELETE" });
          replaceTrip(result.trip);
          setShareCode("");
        } catch (err) {
          setError(err.message);
        }
      },
    });
  }

  function stopSharing(trip) {
    setConfirming({
      eyebrow: "STOP SHARING",
      title: "Stop sharing this trip?",
      message: "Everyone you shared it with will lose access, and the share code will stop working. The trip stays in your trips.",
      confirmLabel: "Stop Sharing",
      onConfirm: async () => {
        try {
          const result = await api(`/api/trips/${trip.id}/share`, { method: "DELETE" });
          replaceTrip(result.trip);
          setShareCode("");
        } catch (err) {
          setError(err.message);
        }
      },
    });
  }

  const tools = [
    { name: "Recommendations", icon: "heart", description: "Hotels, restaurants and activities", path: "recommendations" },
    { name: "Itineraries", icon: "calendar", description: "Plan each day of your trip", path: "itineraries" },
    { name: "Budget", icon: "wallet", description: "Track expenses and spending", path: "budget" },
    { name: "Flight Alerts", icon: "plane", description: "Flight status and updates", path: "flights" },
    { name: "Weather", icon: "sun", description: "Forecasts for your destination", path: "weather" },
    { name: "Airport Data", icon: "airport", description: "Nearby airport information", path: "airports" },
  ];

  return (
    <section className="trips-page">
      <header className="trips-hero">
        <div><span className="trips-eyebrow">✈ YOUR TRAVEL PLANS</span><h1>{selectedTrip ? selectedTrip.destination : "My Trips"}</h1><p>{selectedTrip ? `${formatDate(selectedTrip.start_date)} – ${formatDate(selectedTrip.end_date)}` : "Your adventures, all in one place."}</p></div>
        <div className="trips-hero-actions">
          {!selectedTrip && <button type="button" className="trips-secondary" onClick={() => { setJoining((value) => !value); setCreating(false); }}>{joining ? "Cancel" : "Add Shared Trip"}</button>}
          <button type="button" className="trips-primary" onClick={() => { if (selectedTrip) { onNavigate("/trips"); } else { setCreating((value) => !value); setJoining(false); } }}>{selectedTrip ? "← All Trips" : creating ? "Cancel" : "+ Create New Trip"}</button>
        </div>
      </header>

      {editingCategory && (() => {
        const group = PREFERENCE_GROUPS.find((item) => item.key === editingCategory);
        const chosen = customPreferences[editingCategory] || [];
        const allOptions = [...group.options, ...chosen.filter((item) => !group.options.some((option) => option.toLowerCase() === item.toLowerCase()))];
        const filtered = allOptions.filter((item) => item.toLowerCase().includes(preferenceSearch.trim().toLowerCase()));
        return <div className="trips-editor-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) closeEditor(false); }}>
          <section className="trips-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="trips-editor-title">
            <div className="trips-editor-header">
              <div><span className="trips-editor-eyebrow">TRIP PREFERENCES</span><h2 id="trips-editor-title">{group.label}</h2><p>Select from all available options or add your own.</p></div>
              <button type="button" className="trips-editor-close" onClick={() => closeEditor(false)} aria-label="Cancel and close editor">×</button>
            </div>
            <div className="trips-editor-content">
              <label className="trips-editor-search-label" htmlFor="trips-editor-search">Search preferences</label>
              <input id="trips-editor-search" className="trips-editor-search" type="search" value={preferenceSearch} onChange={(event) => setPreferenceSearch(event.target.value)} placeholder={`Search ${group.label.toLowerCase()}...`} />
              <div className="trips-editor-meta">{chosen.length} selected · {group.options.length} predefined options</div>
              <div className="trips-chips trips-editor-chips">
                {filtered.length ? filtered.map((option) => <button type="button" key={option} aria-pressed={chosen.includes(option)} className={chosen.includes(option) ? "selected" : ""} onClick={() => togglePreference(editingCategory, option)}>{chosen.includes(option) ? "✓ " : "+ "}{option}</button>) : <p className="trips-editor-empty">No matches. You can add your own preference below.</p>}
              </div>
              <div className="trips-editor-custom">
                <label htmlFor="trips-editor-custom">Add a custom preference</label>
                <div className="trips-editor-custom-row">
                  <input id="trips-editor-custom" maxLength={100} value={customEntry} onChange={(event) => setCustomEntry(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") addCustomPreference(event); }} placeholder="Something else? Type your own..." />
                  <button type="button" onClick={addCustomPreference} disabled={!customEntry.trim()}>+ Add</button>
                </div>
              </div>
              {editingCategory === "dietary_restrictions" && <p className="trips-editor-caution">Some dietary needs cannot be verified.</p>}
              {editorError && <p className="trips-error" role="alert">{editorError}</p>}
            </div>
            <div className="trips-editor-footer">
              <button type="button" className="trips-editor-clear" onClick={() => setCustomPreferences((old) => ({ ...old, [editingCategory]: [] }))}>Clear selection</button>
              <div><button type="button" className="trips-editor-cancel" onClick={() => closeEditor(false)}>Cancel</button><button type="button" className="trips-primary" onClick={() => closeEditor(true)}>Done ✓</button></div>
            </div>
          </section>
        </div>;
      })()}
      {error && <p className="trips-error" role="alert">{error}</p>}
      {loading ? <p className="trips-loading">Loading your trips...</p> : selectedTripId && !selectedTrip ? <div className="trips-empty">Trip not found. <button type="button" onClick={() => onNavigate("/trips")}>Back to My Trips</button></div> : selectedTrip ? (
        <>
          <div className="trips-detail-card">
            <div className="trips-photo-wrap">
              <img src={selectedTrip.image_url || FALLBACK} alt={`View of ${selectedTrip.destination}`} onError={(event) => { if (!event.currentTarget.src.endsWith(FALLBACK)) event.currentTarget.src = FALLBACK; }} />
              {photoCredit(selectedTrip)}
            </div>
            <div className="trips-detail-info">
              <h2>{selectedTrip.destination}</h2>
              <p className="trips-detail-dates">{formatDate(selectedTrip.start_date)} – {formatDate(selectedTrip.end_date)}</p>
              <p className="trips-detail-meta">
                {selectedTrip.travelers} {selectedTrip.travelers === 1 ? "traveler" : "travelers"} · {selectedTrip.budget == null ? "No budget set" : `$${selectedTrip.budget.toLocaleString()} budget`}
              </p>
              {!selectedTrip.is_owner && <p className="trips-shared-note">Shared with you by {selectedTrip.owner_name}</p>}
            </div>
            <div className="trips-detail-actions">
              {selectedTrip.is_owner
                ? <>
                    <button type="button" className="trips-share" onClick={() => shareTrip(selectedTrip)}>Share Trip</button>
                    <button type="button" className="trips-delete trips-detail-delete" onClick={() => deleteTrip(selectedTrip)}>Delete Trip</button>
                  </>
                : <button type="button" className="trips-delete trips-detail-delete" onClick={() => leaveTrip(selectedTrip)}>Leave Trip</button>}
            </div>
          </div>
          {selectedTrip.is_owner && (shareCode || selectedTrip.members?.length > 0) && (
            <div className="trips-share-panel">
              {shareCode && (
                <div className="trips-share-code-row" role="status">
                  <div>
                    <strong>Share code</strong>
                    <p>Send this code to someone with an AeroLink account. They can enter it under <em>Add Shared Trip</em> on My Trips to see and edit this trip with you.</p>
                  </div>
                  <code className="trips-share-code">{shareCode}</code>
                  <button type="button" className="trips-secondary" onClick={copyShareCode}>{copied ? "Copied ✓" : "Copy"}</button>
                </div>
              )}
              {selectedTrip.members?.length > 0 && (
                <div className="trips-members">
                  <strong>Shared with</strong>
                  <ul>
                    {selectedTrip.members.map((member) => (
                      <li key={member.id}>
                        <span className="trips-member-avatar" aria-hidden="true">{member.name?.charAt(0)?.toUpperCase() || "?"}</span>
                        <span className="trips-member-name">{member.name}</span>
                        <button type="button" className="trips-member-remove" onClick={() => removeMember(selectedTrip, member)}>Remove</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="trips-share-footer">
                <button type="button" className="trips-stop-sharing" onClick={() => stopSharing(selectedTrip)}>Stop Sharing</button>
              </div>
            </div>
          )}
          <h2 className="trips-section-heading">Your Trip Tools</h2>
          <div className="trips-tools">
            {tools.map((tool) => (
              <button type="button" className="trips-tool" key={tool.path} onClick={() => onNavigate(`/trips/${selectedTrip.id}/${tool.path}`)}>
                <span className="trips-tool-icon"><TripIcon name={tool.icon} /></span>
                <span className="trips-tool-content"><strong>{tool.name}</strong><small>{tool.description}</small></span>
                <span className="trips-arrow">→</span>
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          {joining && <form className="trips-create trips-join" onSubmit={joinTrip}>
            <h2>Add a Shared Trip</h2>
            <p>Enter the code the trip owner sent you. The trip will appear in My Trips and stay in sync with theirs.</p>
            <div className="trips-join-row">
              <label>Trip code<input required autoFocus maxLength={9} placeholder="e.g. K7Q2-M9XD" value={joinCode} onChange={(e) => setJoinCode(e.target.value.toUpperCase())} /></label>
              <button className="trips-primary" type="submit" disabled={joinSaving}>{joinSaving ? "Adding..." : "Add Trip →"}</button>
            </div>
          </form>}
          {creating && <form className="trips-create" onSubmit={createTrip}>
            <h2>Plan a New Trip</h2>
            <div className="trips-form-grid">
              <label className="trips-wide">Destination<input required maxLength={200} placeholder="e.g. Rome, Italy" value={form.destination} onChange={(e) => update("destination", e.target.value)} /></label>
              <label>Start Date<input required type="date" value={form.start_date} onChange={(e) => update("start_date", e.target.value)} /></label>
              <label>End Date<input required type="date" min={form.start_date || undefined} value={form.end_date} onChange={(e) => update("end_date", e.target.value)} /></label>
              <label>Budget (USD)<input type="number" min="0" step="0.01" placeholder="Optional" value={form.budget} onChange={(e) => update("budget", e.target.value)} /></label>
              <label>Travelers<input required type="number" min="1" max="100" value={form.travelers} onChange={(e) => update("travelers", e.target.value)} /></label>
            </div>
            <fieldset className="trips-preference-choice"><legend>Travel Preferences</legend><label><input type="radio" name="pref-mode" checked={form.use_saved_preferences} onChange={() => update("use_saved_preferences", true)} /> Use my saved preferences</label><label><input type="radio" name="pref-mode" checked={!form.use_saved_preferences} onChange={() => update("use_saved_preferences", false)} /> Customize for this trip</label></fieldset>
            {!form.use_saved_preferences && (
              <div className="trips-preference-summary">
                <div className="trips-preference-summary-title">
                  <div><h3>Customize for This Trip</h3><p>Start with your saved preferences. Edit any category without changing My Preferences.</p></div>
                  <span className="trips-only-tag">Trip only</span>
                </div>
                {PREFERENCE_GROUPS.map((group) => {
                  const chosen = customPreferences[group.key] || [];
                  return <div className="trips-preference-row" key={group.key}>
                    <span className="trips-preference-icon" aria-hidden="true">{group.icon}</span>
                    <div className="trips-preference-row-text">
                      <strong>{group.label}</strong>
                      <span>{chosen.length ? `${chosen.slice(0, 3).join(", ")}${chosen.length > 3 ? ` +${chosen.length - 3} more` : ""}` : "None selected"}</span>
                    </div>
                    <button type="button" className="trips-edit-preference" onClick={() => openEditor(group.key)} aria-label={`Edit ${group.label}`}>Edit</button>
                  </div>;
                })}
                <p className="trips-preference-note">Your selections will be saved with this trip only.</p>
              </div>
            )}
            <button className="trips-primary" type="submit" disabled={saving}>{saving ? "Creating..." : "Create Trip →"}</button>
          </form>}
          {trips.length ? <div className="trips-grid">{trips.map((trip) => <div className="trips-card" key={trip.id} role="button" tabIndex={0} onKeyDown={(event) => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onNavigate(`/trips/${trip.id}`); } }} onClick={() => onNavigate(`/trips/${trip.id}`)}><div className="trips-photo-wrap"><img src={trip.image_url || FALLBACK} alt={`View of ${trip.destination}`} onError={(e) => { if (!e.currentTarget.src.endsWith(FALLBACK)) e.currentTarget.src = FALLBACK; }} />{photoCredit(trip)}</div><div className="trips-card-body">{!trip.is_owner && <em className="trips-shared-tag">Shared by {trip.owner_name}</em>}<h2>{trip.destination}</h2><p>{formatDate(trip.start_date)} – {formatDate(trip.end_date)}</p><p>{trip.travelers} {trip.travelers === 1 ? "traveler" : "travelers"} · {trip.budget == null ? "Budget not set" : `$${trip.budget.toLocaleString()} budget`}</p><span>Open Trip →</span></div></div>)}</div> : !creating && !joining && <div className="trips-empty"><span>✈</span><h2>Your next adventure starts here</h2><p>Create your first trip to organize plans, recommendations, and travel updates.</p><button type="button" className="trips-primary" onClick={() => setCreating(true)}>+ Create Your First Trip</button></div>}
        </>
      )}
      {confirming && (
        <div className="trips-editor-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget && !confirmBusy) setConfirming(null); }}>
          <section className="trips-editor-dialog trips-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="trips-confirm-title" aria-describedby="trips-confirm-message">
            <div className="trips-editor-header">
              <div><span className="trips-editor-eyebrow">{confirming.eyebrow}</span><h2 id="trips-confirm-title">{confirming.title}</h2></div>
              <button type="button" className="trips-editor-close" onClick={() => setConfirming(null)} disabled={confirmBusy} aria-label="Close dialog">×</button>
            </div>
            <p id="trips-confirm-message" className="trips-confirm-message">{confirming.message}</p>
            <div className="trips-editor-footer trips-confirm-footer">
              <button type="button" className="trips-secondary" autoFocus onClick={() => setConfirming(null)} disabled={confirmBusy}>Cancel</button>
              <button type="button" className="trips-danger" onClick={runConfirm} disabled={confirmBusy}>{confirmBusy ? "Working..." : confirming.confirmLabel}</button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
