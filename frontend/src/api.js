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
