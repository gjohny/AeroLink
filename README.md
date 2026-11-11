# AeroLink: Smart Travel Assistant

AeroLink combines saved trips, travel preferences, and weather information in a
React/Vite frontend with a Flask API and SQLAlchemy database. Local development
uses SQLite.

## What works on this branch

- Registration, login/logout, account settings, password changes, and account deletion.
- Saved travel preferences and trip creation, viewing, and deletion.
- Destination suggestions while typing, with confirmed locations carried into weather setup.
- Departure/destination forecasts and weather along generated outbound/return driving routes.
- Advisories for thunderstorms, rain, snow, freezing precipitation, low visibility, and wind.
- Trip weather summaries, hourly details, destination temperature plots, and saved forecast-change advisories.
- A separate background worker that refreshes forecasts as travel approaches.

**Integration still pending:** the flight, recommendation, itinerary, budget, and
airport tool pages are placeholders on this branch. Weather appears in trip
details and the weather page. Shared assessment functions and weather-event APIs
are ready for Alan and Alexis; connecting them to actual flight recommendations
and the unified alert interface, followed by joint testing, remains outstanding.

## Quick start

Requirements: **Python 3.10+ with scrypt support** (3.12 recommended), **Node.js
18+**, and npm. Internet access is needed to install dependencies and retrieve
live location, weather, and routing data.

From the repository root, where `start.js` is located:

```sh
node start.js
```

The launcher creates `backend/venv`, installs Python/npm dependencies, creates
`backend/.env` from the example if absent, generates a development `SECRET_KEY` if
needed, initializes database tables, and starts the API, frontend, and one weather
worker. Open **http://localhost:5173**. Stop the launcher with **Ctrl-C**.

Flask defaults to port **5000**. If it is occupied, as can happen with macOS AirPlay
Receiver, run:

```sh
AEROLINK_API_PORT=5001 node start.js
```

In PowerShell, set the variable before launching:

```powershell
$env:AEROLINK_API_PORT = "5001"
node start.js
```

The same port setting configures Flask and Vite's `/api` proxy. Set it in the
launching shell; a value only in `backend/.env` will not configure Vite. Use
`AEROLINK_PYTHON` to select a specific supported Python executable if necessary.

## Try the weather feature

1. Register or log in, then open **My Trips → Create New Trip**.
2. Start typing a destination and select a city suggestion. Custom free-text destinations are also accepted.
3. Save the trip and open its **Weather** tool. Confirm a city if the destination is ambiguous.
4. Add a departure city to check both ends of the journey. It is optional for flying and required for driving.
5. Choose Flying or Driving. Flight departure times are optional; driving times default to 9 a.m. in each departure city's local timezone.
6. Read the weather overview and expand **Getting there**, **At your destination**, or **Coming home** for details. Meaningful forecast changes appear as in-app updates.

Forecasts extend **up to 16 days**, and individual measurements can have shorter
coverage. For a trip further away, the page shows an approximate forecast opening
date. To try live forecasts immediately, use a trip within the next week. Missing
or unavailable weather is displayed explicitly.

The worker checks for due trips every five minutes. Forecasts refresh every six
hours, increasing to hourly within 72 hours of the next travel day. Manual refresh
has a one-minute cooldown, and upstream forecasts are cached for 30 minutes.
Closing the browser does not stop monitoring while the worker process is running.

Weather risks are explainable prototype advisories, not confirmed flight delays
or cancellation probabilities. No trained ML model is bundled; optional compatible
model exports are described in the detailed guide.

## Manual development setup

These commands use macOS/Linux shell syntax. On Windows, use a supported Python
such as `py -3.12` to create the environment and activate it with
`venv\Scripts\Activate.ps1` in PowerShell.

### One-time backend setup

```sh
cd backend
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` if `.env` does not exist. The API and worker require
`SECRET_KEY`. If it is not already configured, append a generated value once:

```sh
test -f .env || cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

If `.env` already exists, keep its settings and add `SECRET_KEY` only if missing.
If the installed interpreter has a different command name, substitute that name
for `python3.12`; it must meet the Python requirements above.

### Start three processes

**API terminal**, from `backend` with the virtual environment activated:

```sh
python run.py
```

**Frontend terminal**, from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

**Weather worker terminal**, from `backend` with the same virtual environment and
configuration as the API:

```sh
python -m flask --app run:app weather-worker
```

Use `weather-worker --once` to process currently due trips once and exit. When
using a custom API port, export `AEROLINK_API_PORT` in both the API and frontend
terminals. Run a single weather worker; `node start.js` already starts one.

Verify API/database connectivity at **http://127.0.0.1:5000/api/health** (substitute
5001 if configured). A healthy response is
`{"status":"ok","database":"connected"}`. The frontend opens the AeroLink home
page; `/health` is the optional connection-status view.

## Configuration and database

| Setting | Purpose / default |
| --- | --- |
| `SECRET_KEY` | Flask session signing; required for manual startup, generated by the launcher for development |
| `DATABASE_URL` | SQLAlchemy connection string; default `sqlite:///app.db` |
| `CORS_ORIGINS` | Comma-separated frontend origins; default `http://localhost:5173` |
| `AEROLINK_API_PORT` | API and frontend proxy port, set in the launching shell; default `5000` |
| `AEROLINK_PYTHON` | Optional Python executable override for `start.js` |
| `UNSPLASH_ACCESS_KEY` | Optional destination cover photos; without it, trips use the fallback image |
| `WEATHER_MODEL_MANIFEST` | Optional path to a compatible trained-model export; unset by default |

Backend settings live in `backend/.env`, which is ignored by Git. Weather provider
URLs, thresholds, and worker settings are documented in
[the weather configuration guide](docs/weather.md#configuration-and-storage).
The default Open-Meteo and public OSRM providers support a no-key, noncommercial
prototype; they are rate limited or best effort.

SQLite data is stored at `backend/instance/app.db` by default. Tables are created
on startup. Weather uses additive tables, so existing users and trips need no
reset. `db.create_all()` does **not** migrate changes to existing columns; future
schema changes need a migration strategy. Trip/account deletion also removes
associated weather plans, snapshots, and events.

## Tests and build

Backend, from `backend` with the virtual environment activated:

```sh
python -m unittest discover -s tests -v
```

Frontend, from the repository root after installing npm dependencies:

```sh
npm --prefix frontend test
npm --prefix frontend run build
```

Backend tests use an isolated in-memory database and mocked providers. They cover
weather rules, units, timezones, road sampling, forecast changes, scheduling,
ownership, cleanup, and model compatibility. Frontend tests cover forecast-state
presentation and date handling. The production frontend is generated in
`frontend/dist`.

## Code and API map

```text
backend/
  app/                 Auth, preferences, trips, and API registration
    weather/           Providers, assessment rules, persistence, routes, worker
  tests/               Backend tests
  config.py            Environment configuration
  run.py               Development API entry point
frontend/
  src/pages/           Application pages
  src/components/      Shared location autocomplete and weather summary
  tests/               Frontend presentation tests
  vite.config.js       Development server and /api proxy
start.js               Development launcher: API + frontend + weather worker
```

| API group | Purpose |
| --- | --- |
| `GET /api/health` | API/database connectivity |
| `/api/auth/*` | Register, login, session, logout, password change, account deletion |
| `GET/PUT /api/preferences` | Saved user preferences |
| `GET/POST /api/trips`, `GET/DELETE /api/trips/:id` | Trip management |
| `POST /api/trips/:id/photo` | Optional destination photo refresh |
| `GET /api/weather/locations?q=...` | City suggestions |
| `/api/trips/:id/weather*` | Weather plan, latest forecast, refresh, and read/unread weather events |

User-specific APIs require the login session; weather and trip routes enforce
ownership. Legacy starter task endpoints remain under `/api/tasks`.

- [Weather API contracts, worker behavior, Alan/Alexis integration, and model exports](docs/weather.md)
- [Weather usability and visual design notes](docs/weather-ux.md)
- [Reference-project attribution and license](THIRD_PARTY_NOTICES.md)

## Troubleshooting

| Issue | What to check |
| --- | --- |
| Port 5000 is occupied | Use `AEROLINK_API_PORT=5001` for the launcher, or set the same value in both manual API/frontend terminals. |
| Missing `SECRET_KEY` | Run the launcher or complete the manual `.env` setup. |
| Python/hashlib/scrypt errors | Use Python 3.12 or another supported interpreter. An existing `backend/venv` must also use a compatible Python. |
| Backend unreachable or login requests fail | Check the API process, matching proxy port, and `/api/health`; use the frontend at `http://localhost:5173`. |
| Destination suggestions are unavailable | Check internet/provider availability. Free-text trip creation still works; weather needs a confirmed city. |
| Forecast not available | Check that the trip is within the forecast horizon and has a confirmed destination. |
| Weather does not update while away | Verify the separate worker is running with the same database/configuration as the API. |
| Updates are temporarily unavailable | Check provider/network access; the last successful forecast is retained during outages. |

## Deployment

`node start.js` is a development launcher. For deployment, use a production WSGI
server for `app:create_app()`, serve `frontend/dist`, and route `/api` to Flask.
Run one separately supervised weather worker against the same database. Configure
a persistent `SECRET_KEY`, database, frontend origin, HTTPS, and
`FLASK_ENV=production` for secure session cookies. Use providers appropriate to
the deployment's usage and commercial requirements. Production hosting and
end-to-end teammate integrations are not configured by this branch.
