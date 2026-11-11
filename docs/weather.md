# Trip weather

Open **My Trips → a trip → Weather**. Search for and select the destination and
optionally a departure city. Ambiguous names require an explicit selection.
Destination-only trips work; driving requires both cities. The My Trips creation
form also suggests cities as you type (after two characters). Selecting a suggestion
saves its coordinates/timezone directly into the new trip's weather plan; custom
free-text destinations remain supported. Choose flying or
driving and save. Driving departures default visibly to 09:00 in the respective
departure city's timezone. Overnight drives use elapsed road duration, not a
calendar-day assumption. Arrival flight times are unknown, so city-level arrival
outlooks cover the travel day. Travel dates come from the existing Trip record.

The page starts with a plain-language weather summary, the affected place/time,
and a practical next step. Forecasts are grouped into **Getting there**, **At your
destination**, and **Coming home**. Expand a group for hourly data or route points.
Scores and model-availability diagnostics stay out of the main traveler view.
Known hazards still show alongside partial-coverage and stale-data notices.

The weather form reuses saved destinations and dates, offers autocomplete for
both cities, and asks for a departure city only when needed. Flight departure
times are optional and collapsed; driving times are shown with 09:00 defaults.
Cancel preserves saved details. First-time forecasts check automatically on page
entry when eligible. The page shows one dated explanation for trips beyond the
forecast horizon, without empty risk cards or an update button that cannot help.
Read/unread updates use plain language, with older updates collapsed. The trip
detail summary uses the same presentation. See [the usability review](weather-ux.md).

No flight booking, confirmed status change, or email/push notification is created
by this feature.

## Run

Use Python 3.10+ (3.12 recommended) and the existing `backend/requirements.txt`.
Set `SECRET_KEY` in `backend/.env`. The launcher selects a supported Python;
set `AEROLINK_PYTHON` to override its executable path. `node start.js` installs dependencies, generates
a development session key if absent, initializes the additive tables, and starts
Flask, Vite, and one separate weather worker. Do not run another worker from a web
server hook or Flask debug reloader. Stop the launcher with Ctrl-C.

If port 5000 is occupied (for example by macOS AirPlay Receiver), run
`AEROLINK_API_PORT=5001 node start.js`; Flask and the Vite API proxy both honor this
process environment variable. The default remains 5000. For separate terminals,
export the same value in both shells.

To run the worker independently, from `backend` with the virtualenv active:

```sh
python -m flask --app run:app weather-worker
python -m flask --app run:app weather-worker --once
```

Deploy the continuous command as one separately supervised process alongside the
web application. It must share the same database and configuration. It checks due
plans every five minutes, refreshes every six hours when the next travel day is
more than 72 hours away, and hourly closer to travel. Refresh schedules and
30-minute leases persist across restarts. An expired lease is recoverable after a
crash; an unexpired lease prevents duplicate work. Monitoring runs through the
return drive's estimated arrival (plus a two-hour margin) or the return travel day.

The worker automatically initializes unambiguous destination-only trips entering
the 16-day forecast horizon. Ambiguous trips require setup. Manual refresh is
limited to once per minute; upstream forecasts are cached for 30 minutes. Source
retrieval time and check time are separate. Forecast variables may have shorter
coverage than the maximum horizon. Missing values are never filled with zero.

## Configuration and storage

| Setting | Default |
| --- | --- |
| `WEATHER_FORECAST_URL` (environment) | `https://api.open-meteo.com` |
| `WEATHER_GEOCODING_URL` (environment) | `https://geocoding-api.open-meteo.com` |
| `WEATHER_ROUTING_URL` (environment) | `https://router.project-osrm.org` |
| `WEATHER_MODEL_MANIFEST` (environment) | unset; model estimates unavailable |
| `WEATHER_CACHE_SECONDS` (Flask configuration) | 1800 |
| `WEATHER_WORKER_INTERVAL_SECONDS` (Flask configuration) | 300 |
| `WEATHER_THRESHOLDS` (Flask configuration) | overrides of `rules.DEFAULT_THRESHOLDS` |

Provider base URLs must use HTTPS. Requests have connection/read timeouts and
persisted retry backoff (at least five minutes; numeric Retry-After is honored up
to a day). Forecast cache identity includes coordinates, variables, units, and
provider URL. Public OSRM is best effort; Open-Meteo's free tier is noncommercial
and rate limited. This setup targets a small class prototype. Changing a provider
endpoint does not require changing components. See [Open-Meteo terms](https://open-meteo.com/en/pricing)
and [OSRM usage policy](https://github.com/Project-OSRM/osrm-backend/wiki/Api-usage-policy).

New tables are `weather_plans`, `weather_snapshots`, `weather_events`, and
`weather_provider_cache`. `db.create_all()` adds them; existing User/Trip tables
need no migration or reset. Plan changes increment a revision so old routes and
snapshots cannot silently apply to new coordinates. Trip and account deletion
explicitly clean up associated weather rows, including bulk account deletion.
Expired provider cache entries are pruned; forecast/event history remains until
trip deletion. Long-lived deployments can add a retention policy separately.

## Assessment and change rules

Internal units are Celsius, mm/hour rain, cm/hour snow, metres visibility, and
km/hour wind. The provider's returned units are checked. The UI displays Fahrenheit,
inches/hour, miles, and mph. WMO thunderstorm codes 95/96/99 are high; freezing
precipitation codes 56/57/66/67 are high. Heavy rain codes 65/82 and heavy snow
codes 75/86 are high. Snow codes 71/73/77/85 and fog codes 45/48 are moderate.

| Numeric condition | Moderate | High |
| --- | --- | --- |
| Rain | ≥2.5 mm/h | ≥7.5 mm/h |
| Snow | >0 cm/h | ≥1 cm/h |
| Visibility | <5000 m | <1000 m |
| Sustained wind | ≥35 km/h | ≥50 km/h |
| Gusts | ≥50 km/h | ≥70 km/h |

A family contributes once per hour: 15 moderate, 35 high, 40 for thunderstorms.
The sum is capped at 100. Window summaries preserve peak hourly score, highest
severity, and each hazard's strongest explanation. These configurable prototype
heuristics are not aviation operating limits or cancellation probabilities.
Flight and driving contexts share the weather rules but assess different places
and travel windows; route risks are sampled, not continuous road monitoring.

OSRM supplies full road geometry and per-edge durations. Sample points follow the
road at approximately hourly intervals, include both endpoints, and are capped at
25 per direction. Each sample checks its estimated passage hour. Long drives use
coarser sampling at the cap. Times at route points are displayed in the departure
city's timezone. Route drawings are schematic, without background map tiles.
Routes exclude live traffic, planned breaks, closures, and road-surface observations.

Change detection compares overlapping future UTC hours at matching locations
within the same plan revision. Both observations must have complete risk inputs.
It records new/removed hazards, severity changes, absolute score changes ≥20, and
high-risk onset shifts ≥3 hours. The first snapshot establishes a baseline.
Newly available hours do not count as changes. Missing/failed observations never
count as improvement. Partial failures retain affected previous windows marked
stale. Each comparison produces at most one event per changed window, with a
persistent dedupe key; subsequent identical forecasts do not repeat events.

## API and team integration

All routes require the existing login session. Trip/event access is checked
against the signed-in user; unknown or another user's trip returns 404.

| Method | Endpoint | Result |
| --- | --- | --- |
| GET | `/api/weather/locations?q=Denver` | `{locations: [...]}` |
| GET | `/api/trips/:id/weather-plan` | `{plan, revision}`; plan may be null |
| PUT | `/api/trips/:id/weather-plan` | save plan; `{plan, revision}` |
| GET | `/api/trips/:id/weather` | latest forecast, status, schedule, setup/lease state |
| POST | `/api/trips/:id/weather/refresh` | check now; same result plus `refreshed` |
| GET | `/api/trips/:id/weather/events` | latest 100 events, newest first |
| POST | `/api/trips/:id/weather/events/:event_id/read` | `{event}` |

Trip creation also accepts optional `destination_location` with the selected
`{label, latitude, longitude, timezone}` to initialize a destination-only weather
plan in the same transaction. Omitting it preserves free-text trip creation.

Plan input contains `destination`, optional `origin`, `mode` (`flight` or
`driving`), and optional `outbound_time` / `return_time` (`HH:MM`). Locations use
`{label, latitude, longitude, timezone}` from search results. Times use the leg's
departure timezone; nonexistent spring-forward times are rejected, and ambiguous
fall-back times use the first occurrence.

The forecast contains `source`, `retrieved_at`, `checked_at`, `windows`, `flight`,
`driving`, `routes`, `model`, `errors`, and `revision`. Each window includes UTC
bounds, location timezone, category, status, coverage, hourly observations and
hazards, and a summary. Unknown scores are null. GET does not perform a full
refresh; manual refresh/worker performs provider I/O. A plan edit can return 409
while refreshing; refresh can return 429 within its one-minute cooldown.

**Alan:** import `app.weather.service.assess_forecast(location, start, end)`.
Use airport coordinates/timezone from your data and increasing timezone-aware
scheduled flight bounds. It returns the same observations, coverage, reasons,
and summary used in the page. City outlooks can therefore be replaced with exact
airport windows without changing the scoring service. `airportsdb` is not merged
or required by this branch.

**Alexis:** `WeatherEvent.to_dict()` provides `type`, `message`, `detail`,
`dedupe_key`, `created_at`, `is_read`, `trip_id`, and `severity`. Consume this
trip-owned event API from the future alert widget. The existing `feature/alerts`
branch's global flight alerts are not merged; do not insert weather into its
flight-number-only schema or expose other users' trip advisories. `detail` is
structured JSON containing changed hours and optional onset shifts. Weather
advisories never change confirmed flight status. Recommendations can consume
`forecast.flight` / `forecast.driving` and reuse `WeatherSummary.jsx` with its
`forecast` prop to avoid an extra request.

## Optional trained model export

No model is bundled and no new training runs automatically. The reference
[notebook](https://github.com/Pranav379/southwest-weather-score-project/blob/main/Modeling/Modeling.ipynb)
saves an H5 file to Google Drive, and its historical score uses observed delay
outcomes. That file alone is insufficient: inference also requires the original
feature order, compatible preprocessing, units, target semantics, and validation
on held-out **forecast** inputs. Outcome-derived features such as WeatherDelay
are rejected. An incompatible model remains unavailable while live rules work.

Set `WEATHER_MODEL_MANIFEST` to an absolute path to a trusted JSON export:

```json
{
  "schema_version": 1,
  "model_version": "your-validated-export-v1",
  "format": "logistic-json",
  "target": "weather_disruption",
  "resolution": "hourly",
  "features": ["rain", "wind_speed_10m"],
  "units": {"rain": "mm/h", "wind_speed_10m": "km/h"},
  "preprocessing": {"means": [0, 0], "scales": [1, 1]},
  "coefficients": [0, 0],
  "intercept": 0,
  "evaluation": {
    "held_out": true,
    "input_kind": "forecast",
    "brier_score": 0.1,
    "baseline_brier_score": 0.2
  }
}
```

This is a **shape example, not trained weights or evaluation results**. Export
actual logistic regression `coef_[0]`, `intercept_[0]`, and the fitted scaler's
means/scales, with positive class 1 meaning weather disruption. Do not label a
regression of delay minutes as a probability. Brier score must improve on the
held-out baseline and metadata must describe the actual evaluation. Keep an
external model card with its dataset and limitations; the adapter checks
compatibility, not the truth of self-reported validation.

Allowed input features are the eight weather variables in `rules.VARIABLES`.
Their manifest units are `celsius`, `percent`, `mm/h`, `cm/h`, `wmo`, `m`, `km/h`,
and `km/h`, respectively. Preprocessing applies `(x - mean) / scale`; use zero and
one for identity. Additional encodings require a new adapter version.

For a compatible Keras binary classifier, set `format` to `keras`, replace
coefficients/intercept with `model_file` pointing to a `.keras` or `.h5` file in
the manifest directory, and install TensorFlow separately. Input is a flat float32
batch in manifest order; output must be one probability per row. Missing runtime,
inputs, artifacts, metadata, or incompatible shapes produce `status: unavailable`
with a reason. The model is optional, does not control alerts, and its displayed
estimate is explicitly scoped to the highest rule-impact assessed flight hour,
not a combined whole-trip probability. See `THIRD_PARTY_NOTICES.md` for attribution.

## Verification

From repository root:

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
npm --prefix frontend test
npm --prefix frontend run build
```

Tests use an in-memory database and mocked providers: thresholds, WMO codes,
missing values, returned units, DST, road timing and point caps, midpoint storms,
return direction, forecast horizon, stale retention, changes/improvements,
deduplication, leases/restarts, revisions, ownership, cleanup, and model parity.
