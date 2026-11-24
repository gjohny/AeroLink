
import { useEffect, useRef, useState } from "react";
import TripPreferenceFields from "../components/TripPreferenceFields";
import "../trips.css";
import "../recs.css";

// Neutral placeholders because Geoapify does not provide
// photos for every location.
function placeholderImage(category) {
  const placeholders = {
    activities: "/images/activity-image.png",
    restaurants: "/images/restaurant-image.png",
    accommodation: "/images/accommodation-image.png",
  };

  return placeholders[category] || placeholders.activities;
}

// Convert Geoapify results to the format expected by
// the existing recommendation cards.
function formatPlace(place, category) {
  const categories = Array.isArray(place.categories)
    ? place.categories
    : [];

  let label = "Attraction";

  if (category === "restaurants") {
    label = "Restaurant";
  } else if (category === "accommodation") {
    label = "Accommodation";
  } else if (categories.includes("entertainment.museum")) {
    label = "Museum";
  } else if (
    categories.some((item) =>
      item.startsWith("tourism.sights.archaeological_site")
    )
  ) {
    label = "Historic site";
  }

  return {
    id: String(place.id),
    name: place.name,
    category,
    detail: place.address || label,
    image: place.photo_url || placeholderImage(category),
    photoCredit: place.photo_credit || "",
    photoSourceUrl: place.photo_source_url || "",
    why: place.why || "A place in your selected destination.",
    address: place.address || "",
    latitude: place.latitude,
    longitude: place.longitude,
    matchScore: place.match_score ?? 0,
    matchedPreferences: place.matched_preferences || [],
    placeCategories: categories,
    catering: place.catering || {},
    facilities: place.facilities || {},
    osmTags: place.osm_tags || {},
    website: place.website || "",
    phone: place.phone || "",
    openingHours: place.opening_hours || "",
  };
}

// Display only explicitly listed attributes; missing data stays unknown.
const FEATURE_LABELS = {
  internet_access: "Internet access",
  air_conditioning: "Air conditioning",
  wheelchair: "Wheelchair access",
  outdoor_seating: "Outdoor seating",
  indoor_seating: "Indoor seating",
  parking: "Parking",
  swimming_pool: "Pool",
  fitness_centre: "Gym",
  kitchen: "Kitchen",
  spa: "Spa",
};

function isAffirmative(value) {
  return value === true || ["yes", "true", "designated", "only"].includes(String(value).toLowerCase());
}

function placeAttributes(place) {
  const tags = place.osmTags || {};
  const facilities = place.facilities || {};
  const listedFacilities = Object.entries(FEATURE_LABELS)
    .filter(([key]) => isAffirmative(facilities[key]) || isAffirmative(tags[key]))
    .map(([, label]) => label);
  const diet = place.catering?.diet || {};
  const dietary = Object.entries(diet)
    .filter(([, value]) => isAffirmative(value))
    .map(([key]) => key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
  const cuisine = typeof tags.cuisine === "string"
    ? tags.cuisine.split(/[;,]/).map((v) => v.trim()).filter(Boolean)
    : [];
  return { listedFacilities, dietary, cuisine };
}

// Rebuild the same details shape from a persisted saved-place record.
function formatSavedPlace(saved) {
  const meta = saved.place_metadata || {};
  return {
    id: saved.place_key,
    name: saved.name,
    category: saved.category,
    detail: saved.detail || "",
    image: saved.image || placeholderImage(saved.category),
    photoCredit: meta.photo_credit || "",
    photoSourceUrl: meta.photo_source_url || "",
    why: saved.why || "Saved for this trip.",
    address: meta.address || saved.detail || "",
    latitude: meta.latitude ?? null,
    longitude: meta.longitude ?? null,
    website: meta.website || "",
    phone: meta.phone || "",
    catering: meta.catering || {},
    facilities: meta.facilities || {},
    osmTags: meta.osm_tags || {},
    placeCategories: meta.categories || [],
  };
}

function safeWebsite(value) {
  if (typeof value !== "string" || !value) return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

const TABS = [
  { id: "activities", label: "Activities" },
  { id: "restaurants", label: "Restaurants" },
  { id: "accommodation", label: "Accommodation" },
];

const dateText = (value) =>
  value
    ? new Date(`${value}T12:00:00`).toLocaleDateString(
        "en-US",
        {
          month: "short",
          day: "numeric",
          year: "numeric",
        }
      )
    : "";

function CategoryIcon({ name, size = 20 }) {
  const shapes = {
    activities: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="m15.5 8.5-2.4 4.6-4.6 2.4 2.4-4.6 4.6-2.4Z" />
      </>
    ),
    restaurants: (
      <>
        <path d="M4 3v7a3 3 0 0 0 6 0V3M7 3v18M17 21V3c-4 2-5 6-5 10h5" />
      </>
    ),
    accommodation: (
      <>
        <rect x="3" y="10" width="18" height="10" rx="2" />
        <path d="M3 15h18M6 10V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v3M3 20v2M21 20v2" />
      </>
    ),
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {shapes[name]}
    </svg>
  );
}

export default function Recommendations({
  tripId,
  onNavigate,
}) {
  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [tab, setTab] = useState("activities");

  const [recommendations, setRecommendations] = useState([]);
  const [recommendationsLoading, setRecommendationsLoading] =
    useState(true);
  const [recommendationsError, setRecommendationsError] =
    useState("");
  const [refreshRecommendations, setRefreshRecommendations] =
    useState(0);

  // Track previously displayed places separately for each tab.
  // The IDs stay in memory for this page visit, not in SQLite.
  const seenIdsRef = useRef({});
  const [refreshRequest, setRefreshRequest] = useState(null);
  const [refreshNotice, setRefreshNotice] = useState("");

  const [savedPlaces, setSavedPlaces] = useState([]);
  const [savingPlace, setSavingPlace] = useState(null);
  const [saveError, setSaveError] = useState("");
  const [itinerarySaving, setItinerarySaving] = useState(false);
  const selectedCount = savedPlaces.filter(place => place.added_to_itinerary).length;
  const allSelected = savedPlaces.length > 0 && selectedCount === savedPlaces.length;
  const activeTripRef = useRef(tripId);
  activeTripRef.current = tripId;

  async function updateItinerary(item, selected) {
    if (itinerarySaving || savingPlace !== null) return;
    const requestedTrip = tripId;
    setItinerarySaving(true);
    setSaveError("");
    try {
      const suffix = item ? `/${item.id}/itinerary` : "/itinerary";
      const res = await fetch(`/api/trips/${tripId}/saved-places${suffix}`, {
        method: "PATCH", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ added_to_itinerary: selected }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !Array.isArray(body.places)) throw new Error(body.error || "Unable to update itinerary selection.");
      if (activeTripRef.current === requestedTrip) {
        const updated = new Map(body.places.map(place => [place.id, place]));
        setSavedPlaces(current => current.map(place => updated.get(place.id) || place));
      }
    } catch (err) {
      if (activeTripRef.current === requestedTrip) setSaveError(err.message);
    } finally {
      setItinerarySaving(false);
    }
  }

  const [showPreferences, setShowPreferences] = useState(false);
  const [draftPreferences, setDraftPreferences] = useState({});
  const [savingPreferences, setSavingPreferences] =
    useState(false);
  const [preferencesError, setPreferencesError] = useState("");

  const [feedback, setFeedback] = useState({});
  const [feedbackSaving, setFeedbackSaving] = useState(null);
  const [feedbackError, setFeedbackError] = useState("");
  const [details, setDetails] = useState(null);

  useEffect(() => {
    seenIdsRef.current = {};
    setRefreshRequest(null);
    setRefreshNotice("");
  }, [tripId]);

  // Load the selected trip.
  useEffect(() => {
    let active = true;

    setLoading(true);
    setError("");

    fetch(`/api/trips/${tripId}`, {
      credentials: "same-origin",
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));

        if (!res.ok) {
          throw new Error(
            body.error || "Unable to load trip."
          );
        }

        return body.trip || body;
      })
      .then((data) => {
        if (active) {
          setTrip(data);
          setDraftPreferences(data.preferences || {});
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [tripId]);

  // Load saved places from SQLite.
  useEffect(() => {
    let active = true;

    setSavedPlaces([]);
    setSaveError("");
    setTab("activities");

    fetch(`/api/trips/${tripId}/saved-places`, {
      credentials: "same-origin",
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));

        if (!res.ok) {
          throw new Error(
            body.error || "Unable to load saved places."
          );
        }

        return body.places || [];
      })
      .then((places) => {
        if (active) setSavedPlaces(places);
      })
      .catch((err) => {
        if (active) setSaveError(err.message);
      });

    return () => {
      active = false;
    };
  }, [tripId]);

  // Load previously saved More/Less feedback for this trip.
  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    setFeedback({});
    setFeedbackError("");

    fetch(`/api/trips/${tripId}/feedback`, {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(body.error || "Unable to load feedback.");
        }
        return body.feedback || [];
      })
      .then((records) => {
        if (!active) return;
        const next = {};
        records.forEach((record) => {
          if (record.preference === "more" || record.preference === "less") {
            next[record.place_key] = record.preference;
          }
        });
        setFeedback(next);
      })
      .catch((err) => {
        if (active && err.name !== "AbortError") {
          setFeedbackError(err.message);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [tripId]);

  // Fetch ranked recommendations. POST excludes previously seen places
  // only when the user explicitly selects "Find New Places".
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const isRefresh = refreshRequest?.category === tab;

    if (!isRefresh) setRecommendations([]);
    setRecommendationsLoading(true);
    setRecommendationsError("");

    const options = {
      credentials: "same-origin",
      signal: controller.signal,
    };
    if (isRefresh) {
      options.method = "POST";
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify({
        excluded_ids: refreshRequest.excludedIds,
      });
    }

    fetch(
      `/api/trips/${tripId}/recommendations?category=${encodeURIComponent(tab)}`,
      options
    )
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(body.error || "Unable to load recommendations.");
        }
        return body;
      })
      .then((body) => {
        if (!active) return;
        const places = body.recommendations || [];
        if (isRefresh && places.length === 0) {
          setRefreshNotice(
            "No additional places are available in the current search results. Your existing recommendations are unchanged."
          );
          return;
        }
        setRecommendations(places.map((place) => formatPlace(place, tab)));
        const seen = new Set(seenIdsRef.current[tab] || []);
        places.forEach((place) => seen.add(String(place.id)));
        seenIdsRef.current[tab] = [...seen];
      })
      .catch((err) => {
        if (active && err.name !== "AbortError") {
          setRecommendationsError(err.message);
        }
      })
      .finally(() => {
        if (active) setRecommendationsLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [tripId, tab, refreshRecommendations]);

  function findNewPlaces() {
    if (recommendationsLoading) return;
    setRefreshNotice("");
    setRefreshRequest({
      category: tab,
      excludedIds: (seenIdsRef.current[tab] || []).slice(0, 200),
    });
    setRefreshRecommendations((value) => value + 1);
  }

  // Save or remove a place.
  async function toggleSaved(item) {
    if (savingPlace !== null || itinerarySaving) return;

    const existing = savedPlaces.find(
      (place) => place.place_key === item.id
    );

    setSavingPlace(item.id);
    setSaveError("");

    try {
      if (existing) {
        const res = await fetch(
          `/api/trips/${tripId}/saved-places/${existing.id}`,
          {
            method: "DELETE",
            credentials: "same-origin",
          }
        );

        const body = await res.json().catch(() => ({}));

        if (!res.ok) {
          throw new Error(
            body.error || "Unable to remove saved place."
          );
        }

        setSavedPlaces((current) =>
          current.filter(
            (place) => place.id !== existing.id
          )
        );
      } else {
        const res = await fetch(
          `/api/trips/${tripId}/saved-places`,
          {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              place_key: item.id,
              name: item.name,
              category: item.category || tab,
              detail: item.detail,
              price: "",
              image: item.image,
              why: item.why,
              place_metadata: {
                address: item.address || "",
                latitude: item.latitude ?? null,
                longitude: item.longitude ?? null,
                website: item.website || "",
                phone: item.phone || "",
                catering: item.catering || {},
                facilities: item.facilities || {},
                osm_tags: item.osmTags || {},
                categories: item.placeCategories || [],
                photo_credit: item.photoCredit || "",
                photo_source_url: item.photoSourceUrl || "",








              },
            }),
          }
        );

        const body = await res.json().catch(() => ({}));

        if (!res.ok) {
          throw new Error(
            body.error || "Unable to save place."
          );
        }

        setSavedPlaces((current) =>
          current.some(
            (place) => place.id === body.place.id
          )
            ? current
            : [...current, body.place]
        );
      }
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSavingPlace(null);
    }
  }

  // Persist feedback and request a newly ranked recommendation list.
  async function handleFeedback(item, choice) {
    if (feedbackSaving !== null) return;

    const currentChoice = feedback[item.id] || null;
    const nextChoice = currentChoice === choice ? null : choice;

    setFeedbackSaving(item.id);
    setFeedbackError("");

    try {
      const res = await fetch(
        `/api/trips/${tripId}/feedback/${encodeURIComponent(item.id)}`,
        {
          method: "PUT",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            preference: nextChoice,
            category: item.category,
            place_categories: item.placeCategories,
          }),
        }
      );

      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error || "Unable to save feedback.");
      }

      setFeedback((old) => {
        const next = { ...old };
        if (nextChoice === null) {
          delete next[item.id];
        } else {
          next[item.id] = nextChoice;
        }
        return next;
      });
      setRefreshRequest(null);
      setRefreshNotice("");
      setRefreshRecommendations((value) => value + 1);
    } catch (err) {
      setFeedbackError(err.message);
    } finally {
      setFeedbackSaving(null);
    }
  }

  // Save updated trip preferences.
  async function savePreferences() {
    setSavingPreferences(true);
    setPreferencesError("");

    try {
      const res = await fetch(
        `/api/trips/${tripId}/preferences`,
        {
          method: "PATCH",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            preferences: draftPreferences,
          }),
        }
      );

      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(
          body.error ||
            "Unable to save trip preferences."
        );
      }

      setTrip(body.trip);
      setDraftPreferences(
        body.trip.preferences || {}
      );
      setShowPreferences(false);

      // A new preference set starts a fresh discovery pool.
      seenIdsRef.current = {};
      setRefreshRequest(null);
      setRefreshNotice("");
      setRefreshRecommendations(
        (value) => value + 1
      );
    } catch (err) {
      setPreferencesError(err.message);
    } finally {
      setSavingPreferences(false);
    }
  }

  const selectedCategory =
    TABS.find((item) => item.id === tab) || TABS[0];

  const cards = recommendations;

  return (
    <section className="recs-page">
      <header className="recs-hero">
        <div>
          <button
            type="button"
            className="recs-back"
            onClick={() =>
              onNavigate(`/trips/${tripId}`)
            }
          >
            ← Back to Trip
          </button>

          <h1>Your Personalized Recommendations</h1>

          <p>
            {trip?.destination || "Your trip"}
            {trip?.start_date && trip?.end_date
              ? ` · ${dateText(
                  trip.start_date
                )} – ${dateText(trip.end_date)}`
              : ""}
          </p>
        </div>

        <button
          type="button"
          className="recs-outline recs-adjust"
          disabled={!trip}
          onClick={() => {
            setDraftPreferences(
              trip?.preferences || {}
            );
            setPreferencesError("");
            setShowPreferences(true);
          }}
        >
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M4 7h16M4 17h16" />
            <circle
              cx="9"
              cy="7"
              r="2"
              fill="white"
            />
            <circle
              cx="15"
              cy="17"
              r="2"
              fill="white"
            />
          </svg>
          Adjust Preferences
        </button>
      </header>

      {loading && (
        <p className="recs-status">
          Loading trip information…
        </p>
      )}

      {error && (
        <p
          className="recs-status recs-error"
          role="alert"
        >
          {error}
        </p>
      )}

      {!loading && !error && (
        <div className="recs-workspace">
          <div className="recs-main">
            <div
              className="recs-tabs"
              role="tablist"
              aria-label="Recommendation categories"
            >
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === item.id}
                  className={
                    tab === item.id ? "active" : ""
                  }
                  onClick={() => {
                    setRefreshNotice("");
                    setRefreshRequest(null);
                    setTab(item.id);
                  }}
                >
                  <CategoryIcon name={item.id} />
                  {item.label}
                </button>
              ))}
            </div>

            <div className="recs-results">
              <div className="recs-results-heading">
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
                  <h2>Recommended {selectedCategory.label}</h2>
                  <button
                    type="button"
                    className="recs-outline"
                    onClick={findNewPlaces}
                    disabled={recommendationsLoading || recommendations.length === 0}
                    aria-label={`Find new ${selectedCategory.label.toLowerCase()}`}
                    style={{ width: "auto", flexShrink: 0, padding: "10px 14px" }}
                  >
                    Find New Places
                  </button>
                </div>

                <p>
                  Explore real places in{" "}
                  {trip?.destination || "your destination"}.
                  Recommendations are ranked using your trip
                  preferences and feedback.
                </p>
              </div>

              {refreshNotice && !recommendationsLoading && (
                <p className="recs-status" role="status">{refreshNotice}</p>
              )}

              {recommendationsError && (
                <p
                  className="recs-status recs-error"
                  role="alert"
                >
                  {recommendationsError}
                </p>
              )}

              {feedbackError && (
                <p className="recs-status recs-error" role="alert">
                  {feedbackError}
                </p>
              )}

              {!recommendationsLoading &&
                !recommendationsError &&
                cards.length === 0 && (
                  <p className="recs-status">
                    No places found for this category
                    and destination.
                  </p>
                )}

              <div className="recs-card-grid">
                {cards.map((item) => {
                  const saved = savedPlaces.some(
                    (place) =>
                      place.place_key === item.id
                  );

                  return (
                    <article
                      className="recs-card"
                      key={item.id}
                    >
                      <img
                        src={item.image}
                        alt={item.name}
                        loading="lazy"
                        onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = placeholderImage(item.category); }}
                      />

                      {item.photoCredit && (
                        <div style={{ fontSize: "11px", padding: "4px 10px", color: "#53657b" }}>
                          Photo: {item.photoSourceUrl ? (
                            <a href={item.photoSourceUrl} target="_blank" rel="noopener noreferrer">{item.photoCredit}</a>
                          ) : item.photoCredit}
                        </div>
                      )}
                      <div className="recs-card-body">
                        <h3>{item.name}</h3>

                        <p className="recs-card-meta">
                          {item.detail}
                        </p>

                        <div className="recs-why">
                          <strong>Why this?</strong>
                          <span>{item.why}</span>
                        </div>

                        <div className="recs-actions">
                          <button
                            type="button"
                            className="recs-blue"
                            disabled={
                              savingPlace !== null || itinerarySaving
                            }
                            onClick={() =>
                              toggleSaved(item)
                            }
                          >
                            {savingPlace === item.id
                              ? "Saving..."
                              : saved
                                ? "✓ Saved"
                                : "Save Place"}
                          </button>

                          <button
                            type="button"
                            className="recs-outline"
                            onClick={() =>
                              setDetails(item)
                            }
                          >
                            View Details
                          </button>
                        </div>

                        <div className="recs-feedback">
                          <button
                            type="button"
                            aria-pressed={feedback[item.id] === "more"}
                            disabled={feedbackSaving !== null}
                            onClick={() => handleFeedback(item, "more")}
                          >
                            {feedbackSaving === item.id
                              ? "Updating..."
                              : "More like this"}
                          </button>

                          <button
                            type="button"
                            aria-pressed={feedback[item.id] === "less"}
                            disabled={feedbackSaving !== null}
                            onClick={() => handleFeedback(item, "less")}
                          >
                            Less like this
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          </div>

          <aside
            className="recs-saved"
            aria-label="Saved places"
          >
            <div className="recs-saved-heading">
              <h2>Saved Places ({savedPlaces.length})</h2>
              {savedPlaces.length > 0 && (
                <button type="button" className="recs-itinerary-all"
                  disabled={itinerarySaving || savingPlace !== null}
                  title={allSelected ? "Deselect all itinerary places" : "Add all saved places to itinerary"}
                  onClick={() => updateItinerary(null, !allSelected)}>
                  {allSelected ? "Deselect all" : "Add all"}
                </button>
              )}
            </div>

            {saveError && (
              <p
                className="recs-error"
                role="alert"
              >
                {saveError}
              </p>
            )}

            <div className="recs-saved-scroll">
              {savedPlaces.length ? (
                savedPlaces.map((item) => (
                  <div
                    className="recs-saved-item"
                    key={item.id}
                  >
                    <img
                      src={
                        item.image ||
                        placeholderImage(
                          item.category
                        )
                      }
                      alt=""
                      onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = placeholderImage(item.category); }}
                    />

                    <button
                      type="button"
                      onClick={() => setDetails(formatSavedPlace(item))}
                      aria-label={`View details for ${item.name}`}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        border: "none",
                        background: "transparent",
                        padding: 0,
                        textAlign: "left",
                        color: "inherit",
                        cursor: "pointer",
                        fontSize: "inherit",
                      }}
                    >
                      <strong>{item.name}</strong>

                      <span>
                        <CategoryIcon
                          name={item.category}
                          size={15}
                        />
                        {
                          TABS.find(
                            (entry) =>
                              entry.id ===
                              item.category
                          )?.label
                        }
                      </span>
                    </button>

                    <button type="button" className="recs-itinerary-toggle"
                      aria-label={`${item.added_to_itinerary ? "Remove from itinerary" : "Add to itinerary"}: ${item.name}`}
                      aria-pressed={Boolean(item.added_to_itinerary)}
                      title={item.added_to_itinerary ? "Remove from itinerary" : "Add to itinerary"}
                      disabled={itinerarySaving || savingPlace !== null}
                      onClick={() => updateItinerary(item, !item.added_to_itinerary)}>
                      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <rect x="3" y="5" width="18" height="16" rx="2" />
                        <path d="M16 3v4M8 3v4M3 10h18" />
                        <path d={item.added_to_itinerary ? "m8 15 3 3 5-5" : "M12 13v5M9.5 15.5h5"} />
                      </svg>
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove ${item.name}`}
                      disabled={
                        savingPlace !== null || itinerarySaving
                      }
                      onClick={() =>
                        toggleSaved({
                          ...item,
                          id: item.place_key,
                        })
                      }
                    >
                      ×
                    </button>
                  </div>
                ))
              ) : (
                <div className="recs-saved-empty">
                  No saved places yet. Choose
                  "Save Place" on a recommendation
                  to bookmark it here.
                </div>
              )}
            </div>
            {savedPlaces.length > 0 && (
              <p className="recs-itinerary-count" role="status">{selectedCount} selected for itinerary</p>
            )}
          </aside>
        </div>
      )}

      {showPreferences && trip && (
        <div
          className="recs-modal-backdrop"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget
            ) {
              setShowPreferences(false);
            }
          }}
        >
          <section
            className="recs-pref-shell"
            role="dialog"
            aria-modal="true"
            aria-label="Adjust trip preferences"
          >
            <div className="recs-pref-shell-header">
              <div>
                <h2>Adjust Trip Preferences</h2>
                <p>
                  Only this trip will be updated.
                  Your account preferences will not
                  change.
                </p>
              </div>

              <button
                type="button"
                className="recs-pref-close"
                onClick={() =>
                  setShowPreferences(false)
                }
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="recs-pref-shell-content">
              <TripPreferenceFields
                preferences={draftPreferences}
                onChange={setDraftPreferences}
                title="Preferences for This Trip"
              />

              {preferencesError && (
                <p
                  className="recs-error"
                  role="alert"
                >
                  {preferencesError}
                </p>
              )}
            </div>

            <div className="recs-pref-shell-footer">
              <button
                type="button"
                className="recs-outline"
                onClick={() =>
                  setShowPreferences(false)
                }
                disabled={savingPreferences}
              >
                Cancel
              </button>

              <button
                type="button"
                className="recs-blue"
                onClick={savePreferences}
                disabled={savingPreferences}
              >
                {savingPreferences
                  ? "Saving..."
                  : "Save Changes"}
              </button>
            </div>
          </section>
        </div>
      )}

      {details && (
        <div
          className="recs-modal-backdrop"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget
            ) {
              setDetails(null);
            }
          }}
        >
          <div
            className="recs-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="recs-modal-title"
          >
            <button
              type="button"
              className="recs-modal-close"
              onClick={() =>
                setDetails(null)
              }
              aria-label="Close"
            >
              ×
            </button>

            <img src={details.image} alt="" onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = placeholderImage(details.category); }} />
            {details.photoCredit && (
              <p style={{ fontSize: "12px" }}>Photo: {details.photoSourceUrl ? (
                <a href={details.photoSourceUrl} target="_blank" rel="noopener noreferrer">{details.photoCredit}</a>
              ) : details.photoCredit}</p>
            )}

            <h2 id="recs-modal-title">{details.name}</h2>

            <div style={{ display: "grid", gap: "14px", margin: "16px 0" }}>
              <div>
                <strong>Address</strong>
                <p style={{ margin: "4px 0" }}>{details.address || "Address unavailable"}</p>
              </div>

              {(() => {
                const { listedFacilities, dietary, cuisine } = placeAttributes(details);
                return (
                  <>
                    {cuisine.length > 0 && (
                      <div><strong>Listed cuisine</strong><p style={{ margin: "4px 0" }}>{cuisine.join(", ")}</p></div>
                    )}
                    {dietary.length > 0 && (
                      <div><strong>Listed dietary options</strong><p style={{ margin: "4px 0" }}>{dietary.join(", ")}</p></div>
                    )}
                    {listedFacilities.length > 0 && (
                      <div><strong>Listed facilities</strong><p style={{ margin: "4px 0" }}>{listedFacilities.join(", ")}</p></div>
                    )}
                  </>
                );
              })()}

              {details.phone && (
                <div><strong>Phone</strong><p style={{ margin: "4px 0" }}>{details.phone}</p></div>
              )}

              <div className="recs-why">
                <strong>Why this?</strong>
                <span>{details.why}</span>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                {(details.name || details.address) && (
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${details.name}, ${details.address || ""}`)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="recs-outline"
                      style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", textDecoration: "none", padding: "10px 14px", width: "auto" }}
                    >
                      View on Google Maps
                    </a>
                  )}
                {safeWebsite(details.website) && (
                  <a
                    className="recs-outline"
                    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", textDecoration: "none", padding: "10px 14px", width: "auto" }}
                    href={safeWebsite(details.website)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    More Info
                  </a>
                )}
              </div>
            </div>

            <p className="recs-modal-note">
              Details come from Geoapify/OpenStreetMap and may be incomplete or outdated.
              Confirm hours, facilities, dietary suitability, and availability with the provider.
            </p>

            <button
              type="button"
              className="recs-blue"
              disabled={savingPlace !== null || itinerarySaving}
              onClick={() =>
                toggleSaved(details)
              }
            >
              {savingPlace === details.id
                ? "Saving..."
                : savedPlaces.some(
                    (place) =>
                      place.place_key === details.id
                  )
                  ? "Remove Saved Place"
                  : "Save Place"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
