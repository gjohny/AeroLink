// All calls use relative /api paths; Vite proxies them to Flask in development.
async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

export const getHealth = () => request("/health");
export const getTasks = () => request("/tasks");
export const createTask = (title) =>
  request("/tasks", { method: "POST", body: JSON.stringify({ title }) });
export const updateTask = (id, changes) =>
  request(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
export const deleteTask = (id) => request(`/tasks/${id}`, { method: "DELETE" });

   export const getAlerts = () => request("/alerts");
   export const markAlertRead = (id) => request(`/alerts/${id}/read`, { method: "POST" });
   export const markAllAlertsRead = () => request("/alerts/read-all", { method: "POST" });

// Airport information comes from OurAirports + local SQLite, not AirLabs.
export const getAirports = (filters = {}) => {
  const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v != null));
  return request(`/airports?${query.toString()}`);
};
export const getAirportByCode = (code) => request(`/airports/${encodeURIComponent(code)}`);

// AirLabs is called exclusively by Flask; the API key stays on the server.
export const getFlights = (filters = {}) => {
  const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v != null));
  return request(`/flights?${query.toString()}`);
};
