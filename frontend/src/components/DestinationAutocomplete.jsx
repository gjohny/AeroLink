import { useEffect, useId, useState } from "react";
import { searchWeatherLocations } from "../weatherApi";

export default function DestinationAutocomplete({
  value, onChange, label = "Destination", selectedLocation = null, required = true,
  allowCustom = true, placeholder = "Start typing a city, e.g. Rome, Italy",
}) {
  const id = useId();
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [selectedValue, setSelectedValue] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [lookup, setLookup] = useState({ query: "", status: "idle", items: [] });
  const query = value.trim();
  const confirmed = value === selectedValue || (!!selectedLocation && value === selectedLocation.label.slice(0, 200));

  useEffect(() => {
    if (!focused || query.length < 2 || confirmed) return;
    const controller = new AbortController();
    let current = true;
    setLookup({ query, status: "loading", items: [] });
    const timer = setTimeout(async () => {
      try {
        const data = await searchWeatherLocations(query, { signal: controller.signal });
        if (current) setLookup({ query, status: "ready", items: data.locations || [] });
      } catch (error) {
        if (current && error.name !== "AbortError") setLookup({ query, status: "error", items: [] });
      }
    }, 300);
    return () => { current = false; clearTimeout(timer); controller.abort(); };
  }, [focused, query, value, confirmed]);

  const items = lookup.query === query ? lookup.items : [];
  const open = focused && !dismissed && query.length >= 2 && !confirmed;
  const loading = open && (lookup.query !== query || lookup.status === "loading");
  const status = loading ? "Finding destinations…" : lookup.status === "error"
    ? (allowCustom ? "Suggestions are unavailable. You can still enter a destination." : "City suggestions are unavailable. Please try again.")
    : !items.length ? (allowCustom ? "No matching cities. Keep typing, or enter your destination directly." : "No matching cities. Try adding a state or country.")
    : `${items.length} destinations found. Use the arrow keys to browse and Enter to select.`;

  function choose(location) {
    const text = location.label.slice(0, 200);
    setSelectedValue(text);
    setDismissed(true);
    setActiveIndex(-1);
    onChange(text, location);
  }

  function handleKeyDown(event) {
    if (event.key === "Escape") {
      setDismissed(true); setActiveIndex(-1);
      event.preventDefault(); event.stopPropagation();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault(); setDismissed(false);
      if (items.length) setActiveIndex((old) => event.key === "ArrowDown"
        ? (old + 1) % items.length : (old <= 0 ? items.length : old) - 1);
    } else if (event.key === "Enter" && open && items.length) {
      event.preventDefault();
      choose(items[activeIndex >= 0 ? activeIndex : 0]);
    }
  }

  useEffect(() => {
    if (open && activeIndex >= 0) document.getElementById(`${id}-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex, id]);

  return <div className="trips-wide trips-destination">
    <label htmlFor={`${id}-input`}>{label}</label>
    <div className="trips-destination-control">
    <input id={`${id}-input`} required={required} maxLength={200} placeholder={placeholder}
      role="combobox" aria-autocomplete="list" aria-expanded={open}
      aria-controls={open ? `${id}-results` : undefined}
      aria-activedescendant={open && activeIndex >= 0 && activeIndex < items.length ? `${id}-option-${activeIndex}` : undefined}
      aria-busy={loading} aria-describedby={`${id}-hint`} autoComplete="off" spellCheck={false}
      value={value} onChange={(event) => {
        setSelectedValue(""); setActiveIndex(-1); setDismissed(false);
        onChange(event.target.value, null);
      }} onFocus={() => { setFocused(true); setDismissed(false); }}
      onBlur={() => { setFocused(false); setActiveIndex(-1); }} onKeyDown={handleKeyDown} />
    {open && <div className="trips-destination-menu">
      <ul id={`${id}-results`} role="listbox" aria-label={`${label} suggestions`}>
        {items.map((location, index) => <li key={location.id || `${location.latitude}-${location.longitude}-${index}`}
          id={`${id}-option-${index}`} role="option" aria-selected={activeIndex === index}
          className={activeIndex === index ? "active" : ""}
          onPointerDown={(event) => event.preventDefault()} onClick={() => choose(location)}>
          <span className="trips-destination-marker" aria-hidden="true">⌖</span>
          <span><strong>{location.name || location.label.split(",")[0]}</strong><small>{location.label}</small></span>
        </li>)}
      </ul>
      {!items.length && <p className="trips-destination-message">{status}</p>}
      {!!items.length && <div className="trips-destination-source">Locations by <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a> / <a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames</a></div>}
    </div>}
    </div>
    <span id={`${id}-hint`} className="trips-destination-hint">{allowCustom ? "Type at least 2 characters for city suggestions, or enter a destination of your own." : "Choose a city from the suggestions."}</span>
    <span className="trips-destination-status" role="status" aria-live="polite">{open ? status : ""}</span>
  </div>;
}
