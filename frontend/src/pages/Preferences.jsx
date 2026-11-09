import { useEffect, useState } from "react";
import "../preference.css";

import { INTERESTS, CUISINES, DIETARY, ACCOMMODATIONS, AMENITIES } from "../data/preferenceOptions";

const initialPreferences = {
  interests: [],
  cuisines: [],
  dietary_restrictions: [],
  accommodation_types: [],
  amenities: []
};

const TABS = [
  { id: "activities", label: "Activities", icon: "♡" },
  { id: "food", label: "Food", icon: "♨" },
  { id: "accommodation", label: "Accommodation", icon: "⌂" }
];

function PreferenceChips({ options, selected, onToggle, onAddCustom }) {
  const [customText, setCustomText] = useState("");
  const allOptions = [...options, ...selected.filter(
    (item) => !options.some((option) => option.toLowerCase() === item.toLowerCase())
  )];

  function addCustom(event) {
    event.preventDefault();
    const value = customText.trim().replace(/\s+/g, " ");
    if (!value || value.length > 100) return;
    const existing = allOptions.find((item) => item.toLowerCase() === value.toLowerCase());
    if (existing) {
      if (!selected.includes(existing)) onToggle(existing);
    } else {
      onAddCustom(value);
    }
    setCustomText("");
  }

  return (
    <div>
      <div className="preference-chips">
        {allOptions.map((option) => (
          <button
            key={option}
            type="button"
            className={`preference-chip ${selected.includes(option) ? "selected" : ""}`}
            aria-pressed={selected.includes(option)}
            onClick={() => onToggle(option)}
          >
            {selected.includes(option) ? "✓ " : "+ "}{option}
          </button>
        ))}
      </div>
      <div className="preferences-custom-entry">
        <input
          type="text"
          maxLength={100}
          aria-label="Add a custom preference"
          placeholder="Something else? Type your own preference"
          value={customText}
          onChange={(event) => setCustomText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") addCustom(event);
          }}
        />
        <button type="button" onClick={addCustom} disabled={!customText.trim()}>
          + Add
        </button>
      </div>
    </div>
  );
}

export default function Preferences({ user }) {
  const [preferences, setPreferences] = useState(initialPreferences);
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadPreferences() {
      try {
        const response = await fetch("/api/preferences", {
          credentials: "same-origin"
        });
        if (!response.ok) throw new Error("Could not load your preferences.");
        const data = await response.json();
        if (active && data.preferences) {
          const loaded = {};
          for (const field of Object.keys(initialPreferences)) {
            loaded[field] = Array.isArray(data.preferences[field])
              ? data.preferences[field]
              : [];
          }
          setPreferences(loaded);
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }

    loadPreferences();
    return () => { active = false; };
  }, []);

  function toggleOption(field, option) {
    setPreferences((previous) => ({
      ...previous,
      [field]: previous[field].includes(option)
        ? previous[field].filter((item) => item !== option)
        : [...previous[field], option]
    }));
    setHasChanges(true);
    setMessage("");
    setError("");
  }

  function addCustomOption(field, value) {
    setPreferences((previous) => {
      if (previous[field].length >= 50) return previous;
      if (previous[field].some((item) => item.toLowerCase() === value.toLowerCase())) return previous;
      return { ...previous, [field]: [...previous[field], value] };
    });
    setHasChanges(true);
    setMessage("");
    setError("");
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/preferences", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(preferences)
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Could not save your preferences.");
      }
      setHasChanges(false);
      setMessage("Your default travel preferences have been saved!");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="preferences-loading">Loading preferences...</div>;
  }

  return (
    <section className="preferences-page preferences-tabs-page">
      <form onSubmit={handleSave}>
        <header className="preferences-tabs-header">
          <div>
            <div className="preferences-eyebrow">✈ PERSONALIZE YOUR JOURNEY</div>
            <h1>My Travel Preferences</h1>
            <p>
              Hi, {user?.name || "traveler"}! Save your travel style and reuse it
              when planning future trips.
            </p>
          </div>
          <button type="submit" className="preferences-save preferences-tabs-save" disabled={saving}>
            {saving ? "Saving..." : hasChanges ? "Save Changes →" : "Save Preferences →"}
          </button>
        </header>

        <div className="preferences-tabs-status" aria-live="polite">
          {message && <p className="preferences-success" role="status">✓ {message}</p>}
          {error && <p className="preferences-error" role="alert">{error}</p>}
          {!message && !error && hasChanges && (
            <p className="preferences-unsaved">You have unsaved changes.</p>
          )}
        </div>

        <div className="preferences-tab-strip" role="tablist" aria-label="Preference categories">
          {TABS.map((tab, index) => (
            <button
              key={tab.id}
              id={`preferences-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={activeTab === index}
              aria-controls={`preferences-panel-${tab.id}`}
              tabIndex={activeTab === index ? 0 : -1}
              className={`preferences-tab ${activeTab === index ? "is-active" : ""}`}
              onClick={() => setActiveTab(index)}
              onKeyDown={(event) => {
                if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const next = event.key === "Home" ? 0
                  : event.key === "End" ? TABS.length - 1
                  : (activeTab + (event.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length;
                setActiveTab(next);
                document.getElementById(`preferences-tab-${TABS[next].id}`)?.focus();
              }}
            >
              <span className="preferences-tab-icon" aria-hidden="true">{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        <div
          id={`preferences-panel-${TABS[activeTab].id}`}
          role="tabpanel"
          aria-labelledby={`preferences-tab-${TABS[activeTab].id}`}
          tabIndex={0}
          className="preferences-tab-panel preference-card"
        >
          {activeTab === 0 && (
            <>
              <div className="preference-card-heading">
                <div className="preference-card-icon">♡</div>
                <div>
                  <h2>Activities & Interests</h2>
                  <p>What do you enjoy doing when you travel?</p>
                </div>
              </div>
              <PreferenceChips
                options={INTERESTS}
                selected={preferences.interests}
                onToggle={(option) => toggleOption("interests", option)}
                onAddCustom={(value) => addCustomOption("interests", value)}
              />
              <div className="preference-tip">
                Select as many as you like. We'll use these for personalized activity recommendations.
              </div>
            </>
          )}

          {activeTab === 1 && (
            <>
              <div className="preference-card-heading">
                <div className="preference-card-icon">♨</div>
                <div>
                  <h2>Food Preferences</h2>
                  <p>Discover food you'll love.</p>
                </div>
              </div>
              <h3>Favorite Cuisines</h3>
              <PreferenceChips
                options={CUISINES}
                selected={preferences.cuisines}
                onToggle={(option) => toggleOption("cuisines", option)}
                onAddCustom={(value) => addCustomOption("cuisines", value)}
              />
              <h3>Dietary Restrictions</h3>
              <p className="preferences-dietary-note">Some dietary needs cannot be verified.</p>
              <PreferenceChips
                options={DIETARY}
                selected={preferences.dietary_restrictions}
                onToggle={(option) => toggleOption("dietary_restrictions", option)}
                onAddCustom={(value) => addCustomOption("dietary_restrictions", value)}
              />
            </>
          )}

          {activeTab === 2 && (
            <>
              <div className="preference-card-heading">
                <div className="preference-card-icon">⌂</div>
                <div>
                  <h2>Accommodation</h2>
                  <p>Find your ideal place to stay.</p>
                </div>
              </div>
              <h3>Preferred Accommodation Types</h3>
              <PreferenceChips
                options={ACCOMMODATIONS}
                selected={preferences.accommodation_types}
                onToggle={(option) => toggleOption("accommodation_types", option)}
                onAddCustom={(value) => addCustomOption("accommodation_types", value)}
              />
              <h3>Preferred Amenities</h3>
              <PreferenceChips
                options={AMENITIES}
                selected={preferences.amenities}
                onToggle={(option) => toggleOption("amenities", option)}
                onAddCustom={(value) => addCustomOption("amenities", value)}
              />
            </>
          )}
        </div>

        <div className="preferences-tabs-footer">
          <button
            type="button"
            className="preferences-tabs-back"
            disabled={activeTab === 0}
            onClick={() => setActiveTab((tab) => Math.max(0, tab - 1))}
          >
            ← Previous
          </button>
          <span className="preferences-tabs-step">{activeTab + 1} of {TABS.length}</span>
          {activeTab < TABS.length - 1 ? (
            <button
              type="button"
              className="preferences-tabs-next"
              onClick={() => setActiveTab((tab) => Math.min(TABS.length - 1, tab + 1))}
            >
              Next: {TABS[activeTab + 1].label} →
            </button>
          ) : (
            <button type="submit" className="preferences-save preferences-tabs-save" disabled={saving}>
              {saving ? "Saving..." : "Save Preferences →"}
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
