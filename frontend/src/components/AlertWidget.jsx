import { useCallback, useEffect, useRef, useState } from "react";
import { getAlerts, markAlertRead, markAllAlertsRead } from "../api.js";
import "./AlertWidget.css";

const POLL_MS = 30000;

const TYPE_LABELS = {delay: "Delay", gate_change: "Gate change", cancellation: "Cancelled"};

function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1){ 
    return "Just now";
  }

  if (minutes < 60){
    return `${minutes} min ago`;
  }

  const hours = Math.round(minutes / 60);

  if (hours < 24){
    return `${hours} hr ago`;
  }

  return new Date(iso).toLocaleDateString();
}

function BellIcon() {
  return (
    <svg width = "24" height = "24" viewBox = "0 0 24 24" fill = "none" stroke = "currentColor" strokeWidth = "2" strokeLinecap = "round" strokeLinejoin = "round" aria-hidden = "true">
      <path d = "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d = "M13.7 21a2 2 0 0 1-3.4 0" />
    </svg>
  );
}

export default function AlertWidget() {
  const [alerts, setAlerts] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [justArrived, setJustArrived] = useState(false);
  const lastUnread = useRef(0);

  const unread = alerts.filter((a) => !a.is_read).length;

  const refresh = useCallback(async () => {
    try {
      setAlerts(await getAlerts());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoaded(true);
    }
  }, []);

  //Load on mount, then poll. Also refresh when the tab becomes visible again
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible"){
        refresh();
      }
    };

    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  //Give the badge a short pulse when new unread alerts show up
  useEffect(() => {
    if (unread > lastUnread.current) {
      setJustArrived(true);
      const t = setTimeout(() => setJustArrived(false), 2500);
      lastUnread.current = unread;
      return () => clearTimeout(t);
    }

    lastUnread.current = unread;
  }, [unread]);

  //Escape minimizes the panel
  useEffect(() => {
    if (!open){
      return undefined;
    }

    const onKey = (event) => {
      if (event.key === "Escape"){
        setOpen(false);
      }
    };

    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  async function openAlert(alert) {
    setExpandedId(expandedId === alert.id ? null : alert.id);
    if (alert.is_read) return;

    try {
      const updated = await markAlertRead(alert.id);
      setAlerts((current) => current.map((a) => (a.id === updated.id ? updated : a)));
    } catch {
      setError(true);
    }
  }

  async function readAll() {
    try {
      await markAllAlertsRead();
      setAlerts((current) => current.map((a) => ({ ...a, is_read: true })));
    } catch {
      setError(true);
    }
  }

  const bellLabel = unread > 0 ? `Alerts, ${unread} unread` : "Alerts, none unread";

  return (
    <div className="alert-widget">
      {open && (
        <section className = "alert-panel" aria-label = "Flight alerts">
          <header className = "alert-panel-header">
            <h2>Alerts{unread > 0 && <span className = "alert-new-count">{unread} new</span>}</h2>
            {unread > 0 && (
              <button type = "button" className = "alert-link-button" onClick = {readAll}>
                Mark all as read
              </button>
            )}
          </header>

          {error && (
            <p className = "alert-message alert-message-error" role = "status">
              Can't reach the alert service. Retrying
            </p>
          )}

          {!error && loaded && alerts.length === 0 && (
            <p className = "alert-message">No alerts yet. We'll let you know if something changes</p>
          )}

          <ul className = "alert-list">
            {alerts.map((alert) => (
              <li key = {alert.id}>
                <button type = "button" className = {`alert-item${alert.is_read ? "" : " alert-item-unread"}`} aria-expanded = {expandedId === alert.id} onClick = {() => openAlert(alert)}>
                  <span className = {`alert-chip alert-chip-${alert.alert_type}`}>
                    {TYPE_LABELS[alert.alert_type] || "Update"}
                  </span>
                  <span className = "alert-text">{alert.message}</span>
                  <span className = "alert-time">{timeAgo(alert.created_at)}</span>
                  {expandedId === alert.id && alert.detail && (
                    <span className = "alert-detail">
                      <strong>What changed</strong> {alert.detail}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <button type = "button" className = "alert-bell" aria-label = {bellLabel} aria-expanded = {open} title = {bellLabel} onClick = {() => setOpen((value) => !value)}>
        <BellIcon />
        {unread > 0 && (
          <span className = {`alert-badge${justArrived ? " alert-badge-pulse" : ""}`} aria-hidden = "true">
            !
          </span>
        )}
      </button>
    </div>
  );
}
