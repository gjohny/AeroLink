import { useState } from "react";
import { PREFERENCE_GROUPS } from "../data/preferenceOptions";

// The same editor is used during trip creation and from Recommendations.
export default function TripPreferenceFields({ preferences, onChange, title = "Customize for This Trip" }) {
  const [editingCategory, setEditingCategory] = useState(null);
  const [backup, setBackup] = useState(null);
  const [search, setSearch] = useState("");
  const [customEntry, setCustomEntry] = useState("");
  const [error, setError] = useState("");

  function openEditor(key) {
    setBackup(Object.fromEntries(PREFERENCE_GROUPS.map(({ key }) => [key, [...(preferences[key] || [])]])));
    setEditingCategory(key);
    setSearch("");
    setCustomEntry("");
    setError("");
  }
  function closeEditor(keep) {
    if (!keep && backup) onChange(backup);
    setEditingCategory(null);
    setBackup(null);
    setSearch("");
    setCustomEntry("");
    setError("");
  }
  function toggle(key, option) {
    const current = preferences[key] || [];
    if (!current.includes(option) && current.length >= 50) {
      setError("You can select up to 50 preferences in this category.");
      return;
    }
    setError("");
    onChange({ ...preferences, [key]: current.includes(option) ? current.filter(v => v !== option) : [...current, option] });
  }
  function addCustom(event) {
    event.preventDefault();
    const value = customEntry.trim().replace(/\s+/g, " ");
    if (!value || !editingCategory) return;
    if (value.length > 100) { setError("Custom preferences must be 100 characters or fewer."); return; }
    const group = PREFERENCE_GROUPS.find(g => g.key === editingCategory);
    const all = [...group.options, ...(preferences[editingCategory] || [])];
    const existing = all.find(item => item.toLowerCase() === value.toLowerCase());
    if (existing) {
      if (!(preferences[editingCategory] || []).includes(existing)) toggle(editingCategory, existing);
    } else toggle(editingCategory, value);
    setCustomEntry("");
  }
  const group = PREFERENCE_GROUPS.find(g => g.key === editingCategory);
  const chosen = editingCategory ? (preferences[editingCategory] || []) : [];
  const allOptions = group ? [...group.options, ...chosen.filter(item => !group.options.some(option => option.toLowerCase() === item.toLowerCase()))] : [];
  const filtered = allOptions.filter(item => item.toLowerCase().includes(search.trim().toLowerCase()));
  return <>
    <div className="trips-preference-summary">
      <div className="trips-preference-summary-title">
        <div><h3>{title}</h3><p>Edit any category, including your custom choices, without changing account preferences.</p></div>
        <span className="trips-only-tag">Trip only</span>
      </div>
      {PREFERENCE_GROUPS.map(group => {
        const selected = preferences[group.key] || [];
        return <div className="trips-preference-row" key={group.key}>
          <span className="trips-preference-icon" aria-hidden="true">{group.icon}</span>
          <div className="trips-preference-row-text"><strong>{group.label}</strong><span>{selected.length ? `${selected.slice(0, 3).join(", ")}${selected.length > 3 ? ` +${selected.length - 3} more` : ""}` : "None selected"}</span></div>
          <button type="button" className="trips-edit-preference" onClick={() => openEditor(group.key)}>Edit</button>
        </div>;
      })}
      <p className="trips-preference-note">These selections belong to this trip only.</p>
    </div>
    {group && <div className="trips-editor-overlay" onMouseDown={e => { if (e.target === e.currentTarget) closeEditor(false); }}>
      <section className="trips-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="trips-editor-title">
        <div className="trips-editor-header"><div><span className="trips-editor-eyebrow">TRIP PREFERENCES</span><h2 id="trips-editor-title">{group.label}</h2><p>Select from all available options or add your own.</p></div><button type="button" className="trips-editor-close" onClick={() => closeEditor(false)} aria-label="Cancel and close editor">×</button></div>
        <div className="trips-editor-content">
          <label className="trips-editor-search-label" htmlFor="trips-editor-search">Search preferences</label>
          <input id="trips-editor-search" className="trips-editor-search" type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder={`Search ${group.label.toLowerCase()}...`} />
          <div className="trips-editor-meta">{chosen.length} selected · {group.options.length} predefined options</div>
          <div className="trips-chips trips-editor-chips">{filtered.length ? filtered.map(option => <button type="button" key={option} aria-pressed={chosen.includes(option)} className={chosen.includes(option) ? "selected" : ""} onClick={() => toggle(editingCategory, option)}>{chosen.includes(option) ? "✓ " : "+ "}{option}</button>) : <p className="trips-editor-empty">No matches. Add your own below.</p>}</div>
          <form className="trips-editor-custom" onSubmit={addCustom}><label htmlFor="trips-editor-custom">Add a custom preference</label><div className="trips-editor-custom-row"><input id="trips-editor-custom" maxLength={100} value={customEntry} onChange={e => setCustomEntry(e.target.value)} placeholder="Something else? Type your own..." /><button type="submit" disabled={!customEntry.trim()}>+ Add</button></div></form>
          {editingCategory === "dietary_restrictions" && <p className="trips-editor-caution">Some dietary needs cannot be verified.</p>}
          {error && <p className="trips-error" role="alert">{error}</p>}
        </div>
        <div className="trips-editor-footer"><button type="button" className="trips-editor-clear" onClick={() => onChange({ ...preferences, [editingCategory]: [] })}>Clear selection</button><div><button type="button" className="trips-editor-cancel" onClick={() => closeEditor(false)}>Cancel</button><button type="button" className="trips-primary" onClick={() => closeEditor(true)}>Done ✓</button></div></div>
      </section>
    </div>}
  </>;
}
