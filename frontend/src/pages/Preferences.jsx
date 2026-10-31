
import { useEffect, useState } from "react";

const INTERESTS = [
  "Beaches", "Museums", "Hiking", "Shopping",
  "Nightlife", "Nature", "History", "Adventure",
  "Art", "Relaxation", "Family Activities", "Food Tours"
];

const CUISINES = [
  "Italian", "Mexican", "Indian", "Chinese",
  "Japanese", "Thai", "Mediterranean", "American",
  "French", "Korean"
];

const DIETARY = [
  "Vegetarian", "Vegan", "Halal", "Kosher",
  "Gluten-Free", "Dairy-Free", "Nut-Free"
];

const ACCOMMODATIONS = [
  "Hotel", "Resort", "Apartment", "Hostel",
  "Vacation Rental", "Bed & Breakfast"
];

const AMENITIES = [
  "Wi-Fi", "Parking", "Pool", "Gym",
  "Breakfast Included", "Pet-Friendly",
  "Kitchen", "Air Conditioning"
];

const initialPreferences = {
  destination: "",
  start_date: "",
  end_date: "",
  budget: "",
  travelers: 1,
  interests: [],
  cuisines: [],
  dietary_restrictions: [],
  accommodation_types: [],
  amenities: []
};

function PreferenceChips({ options, selected, onToggle }) {
  return (
    <div className="preference-chips">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={`preference-chip ${
            selected.includes(option) ? "selected" : ""
          }`}
          aria-pressed={selected.includes(option)}
          onClick={() => onToggle(option)}
        >
          {selected.includes(option) ? "✓ " : "+ "}
          {option}
        </button>
      ))}
    </div>
  );
}

export default function Preferences({ user }) {
  const [preferences, setPreferences] = useState(initialPreferences);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadPreferences() {
      try {
        const response = await fetch("/api/preferences", {
          credentials: "same-origin"
        });

        if (!response.ok) {
          throw new Error("Could not load your preferences.");
        }

        const data = await response.json();

        if (active && data.preferences) {
          setPreferences({
            ...initialPreferences,
            ...data.preferences,
            start_date: data.preferences.start_date || "",
            end_date: data.preferences.end_date || "",
            budget: data.preferences.budget ?? ""
          });
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }

    loadPreferences();

    return () => {
      active = false;
    };
  }, []);

  function updateField(field, value) {
    setPreferences((previous) => ({
      ...previous,
      [field]: value
    }));
    setMessage("");
  }

  function toggleOption(field, option) {
    setPreferences((previous) => {
      const selected = previous[field];

      return {
        ...previous,
        [field]: selected.includes(option)
          ? selected.filter((item) => item !== option)
          : [...selected, option]
      };
    });

    setMessage("");
  }

  async function handleSave(event) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (
      preferences.start_date &&
      preferences.end_date &&
      preferences.end_date < preferences.start_date
    ) {
      setError("End date cannot be before start date.");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch("/api/preferences", {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          ...preferences,
          start_date: preferences.start_date || null,
          end_date: preferences.end_date || null,
          budget: preferences.budget === ""
            ? null
            : Number(preferences.budget),
          travelers: Number(preferences.travelers)
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Could not save preferences.");
      }

      setMessage("Your travel preferences have been saved!");
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
    <section className="preferences-page">
      <div className="preferences-header">
        <div>
          <div className="preferences-eyebrow">
            ✈ PERSONALIZE YOUR JOURNEY
          </div>

          <h1>Your Travel Preferences</h1>

          <p>
            Hi, {user.name}! Tell us what you love, and we'll help
            you discover places that match your travel style.
          </p>
        </div>

        <div className="preferences-header-icon" aria-hidden="true">
          ✈
        </div>
      </div>

      <form onSubmit={handleSave}>
        <div className="preferences-grid">

          {/* Trip Details */}
          <section className="preference-card">
            <div className="preference-card-heading">
              <div className="preference-card-icon">✈</div>
              <div>
                <h2>Trip Details</h2>
                <p>Where are you headed?</p>
              </div>
            </div>

            <div className="preference-fields">
              <label htmlFor="pref-destination">Destination</label>
              <input
                id="pref-destination"
                type="text"
                placeholder="e.g. San Diego, California"
                maxLength={200}
                value={preferences.destination}
                onChange={(e) =>
                  updateField("destination", e.target.value)
                }
              />

              <div className="preference-two-columns">
                <div>
                  <label htmlFor="pref-start">Start Date</label>
                  <input
                    id="pref-start"
                    type="date"
                    value={preferences.start_date}
                    onChange={(e) =>
                      updateField("start_date", e.target.value)
                    }
                  />
                </div>

                <div>
                  <label htmlFor="pref-end">End Date</label>
                  <input
                    id="pref-end"
                    type="date"
                    min={preferences.start_date || undefined}
                    value={preferences.end_date}
                    onChange={(e) =>
                      updateField("end_date", e.target.value)
                    }
                  />
                </div>
              </div>

              <div className="preference-two-columns">
                <div>
                  <label htmlFor="pref-budget">Total Budget ($)</label>
                  <input
                    id="pref-budget"
                    type="number"
                    min="0"
                    step="0.01"
                    placeholder="1500"
                    value={preferences.budget}
                    onChange={(e) =>
                      updateField("budget", e.target.value)
                    }
                  />
                </div>

                <div>
                  <label htmlFor="pref-travelers">Travelers</label>
                  <input
                    id="pref-travelers"
                    type="number"
                    min="1"
                    max="50"
                    value={preferences.travelers}
                    onChange={(e) =>
                      updateField("travelers", e.target.value)
                    }
                    required
                  />
                </div>
              </div>
            </div>
          </section>

          {/* Interests */}
          <section className="preference-card">
            <div className="preference-card-heading">
              <div className="preference-card-icon">♡</div>
              <div>
                <h2>Activities & Interests</h2>
                <p>What do you enjoy doing?</p>
              </div>
            </div>

            <PreferenceChips
              options={INTERESTS}
              selected={preferences.interests}
              onToggle={(option) => toggleOption("interests", option)}
            />

            <div className="preference-tip">
              Select as many as you like. We'll use these to
              personalize your activity recommendations.
            </div>
          </section>

          {/* Food Preferences */}
          <section className="preference-card">
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
            />

            <h3>Dietary Restrictions</h3>
            <PreferenceChips
              options={DIETARY}
              selected={preferences.dietary_restrictions}
              onToggle={(option) =>
                toggleOption("dietary_restrictions", option)
              }
            />
          </section>

          {/* Accommodation */}
          <section className="preference-card">
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
              onToggle={(option) =>
                toggleOption("accommodation_types", option)
              }
            />

            <h3>Preferred Amenities</h3>
            <PreferenceChips
              options={AMENITIES}
              selected={preferences.amenities}
              onToggle={(option) => toggleOption("amenities", option)}
            />
          </section>
        </div>

        <div className="preferences-bottom">
          <div className="preferences-bottom-info">
            <strong>✦ Made for your travel style</strong>
            <p>
              Your selections help AeroLink recommend lodging,
              activities, and restaurants that suit your trip.
            </p>
          </div>

          <button
            type="submit"
            className="preferences-save"
            disabled={saving}
          >
            {saving ? "Saving..." : "Save Preferences →"}
          </button>
        </div>

        {message && (
          <p className="preferences-success" role="status">
            ✓ {message}
          </p>
        )}

        {error && (
          <p className="preferences-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
