async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Weather request failed (${response.status}).`);
  return body;
}
export const searchWeatherLocations = (query, options) => request(`/weather/locations?q=${encodeURIComponent(query)}`, options);
export const getWeatherPlan = (id, options) => request(`/trips/${id}/weather-plan`, options);
export const saveWeatherPlan = (id, plan) => request(`/trips/${id}/weather-plan`, { method: "PUT", body: JSON.stringify(plan) });
export const getWeather = (id, options) => request(`/trips/${id}/weather`, options);
export const refreshWeather = (id) => request(`/trips/${id}/weather/refresh`, { method: "POST" });
export const getWeatherEvents = (id, options) => request(`/trips/${id}/weather/events`, options);
export const readWeatherEvent = (id, eventId) => request(`/trips/${id}/weather/events/${eventId}/read`, { method: "POST" });
export const getWeatherTrip = (id, options) => request(`/trips/${id}`, options);
