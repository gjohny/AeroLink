# Full Stack App: React + Flask + SQL

A starter project with a **React** frontend (Vite), a **Flask** REST API, and a **SQL** database (SQLite by default, PostgreSQL optional) managed through SQLAlchemy.

The sample app is a simple task list. It shows the full round trip: React UI → Flask API → database, and back.

## Project layout

```
fullstack-app/
├── README.md
├── .gitignore
├── docker-compose.yml        # Optional PostgreSQL container
├── backend/
│   ├── requirements.txt
│   ├── .env.example          # Copy to .env
│   ├── config.py             # Reads DATABASE_URL and CORS settings
│   ├── run.py                # Entry point: starts Flask on port 5000
│   └── app/
│       ├── __init__.py       # App factory, creates tables on startup
│       ├── extensions.py     # SQLAlchemy and CORS instances
│       ├── models.py         # Database models (Task)
│       └── routes.py         # API endpoints under /api
└── frontend/
    ├── package.json
    ├── vite.config.js        # Dev server + proxy of /api to Flask
    ├── index.html
    └── src/
        ├── main.jsx          # React entry point
        ├── App.jsx           # UI
        ├── api.js            # Functions that call the backend
        └── index.css
```

## How the pieces connect

```
Browser (React, :5173)  --/api/*-->  Vite proxy  -->  Flask (:5000)  -->  SQLAlchemy  -->  Database
```

- **Frontend → Backend:** React calls relative URLs such as `/api/tasks`. In development, Vite's proxy (`vite.config.js`) forwards `/api/*` to `http://127.0.0.1:5000`.
- **Backend → Database:** Flask uses SQLAlchemy with the connection string in `backend/.env` (`DATABASE_URL`). Tables are created automatically on startup.
- **Check it works:** the page shows a green "connected" message when the frontend, backend and database are all reachable (it calls `GET /api/health`, which runs `SELECT 1`).

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- (Optional) Docker, only if you want PostgreSQL

## Quick start

You need **two terminals**: one for the backend, one for the frontend.

### 1. Backend (Flask)

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows (PowerShell/CMD)

# Install dependencies
pip install -r requirements.txt

# Create your env file (skip if backend/.env already exists)
cp .env.example .env              # Windows: copy .env.example .env

# Start the API
python run.py
```

The API runs at http://127.0.0.1:5000. Verify it: open http://127.0.0.1:5000/api/health. You should see `{"database":"connected","status":"ok"}`.

On first run, SQLite creates the file `backend/instance/app.db` with the `tasks` table.

### 2. Frontend (React)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. You should see the **Tasks** page with a green message: *Frontend, backend and database are connected*. Add a task, refresh the page, and it will still be there because it is stored in the database.

## Using PostgreSQL instead of SQLite (optional)

1. Start the database from the project root:
   ```bash
   docker compose up -d
   ```
2. In `backend/.env`, comment out the SQLite line and enable the PostgreSQL one:
   ```
   DATABASE_URL=postgresql://appuser:apppassword@localhost:5432/appdb
   ```
3. Restart the backend (`python run.py`). Tables are created automatically.

Stop the database with `docker compose down` (add `-v` to also delete its data).

To use MySQL, change `DATABASE_URL` to `mysql+pymysql://user:password@localhost:3306/dbname` and `pip install pymysql`.

## API reference

| Method | Endpoint           | Description                         | Body                        |
|--------|--------------------|-------------------------------------|-----------------------------|
| GET    | `/api/health`      | API and database status             |                             |
| GET    | `/api/tasks`       | List all tasks                      |                             |
| POST   | `/api/tasks`       | Create a task                       | `{"title": "Buy milk"}`     |
| PATCH  | `/api/tasks/<id>`  | Update title and/or done state      | `{"done": true}`            |
| DELETE | `/api/tasks/<id>`  | Delete a task                       |                             |

Try it from the command line:

```bash
curl -X POST http://127.0.0.1:5000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Test from curl"}'
curl http://127.0.0.1:5000/api/tasks
```

## Building on this starter

- **Add a database table:** define a new class in `backend/app/models.py`. Because the starter uses `db.create_all()`, new tables appear on the next start, but changes to *existing* tables are not applied. When your schema starts changing, add [Flask-Migrate](https://flask-migrate.readthedocs.io/) for proper migrations.
- **Add an endpoint:** add a function with a decorator in `backend/app/routes.py` (for example `@api.get("/things")`).
- **Call it from React:** add a function in `frontend/src/api.js` and use it in your components.
- **Environment variables:** keep secrets in `backend/.env`. It is listed in `.gitignore` so it is never committed.

## Troubleshooting

| Problem | Fix |
|---|---|
| Page says "Backend unreachable" | Make sure `python run.py` is running and nothing else is using port 5000. On macOS, AirPlay Receiver can occupy port 5000: turn it off in System Settings, or change the port in `run.py` **and** the proxy target in `frontend/vite.config.js`. |
| `ModuleNotFoundError` in backend | Activate the virtual environment, then run `pip install -r requirements.txt` again. |
| `psycopg2` install fails | You only need it for PostgreSQL. Remove that line from `requirements.txt` if you're using SQLite, or install your OS's PostgreSQL client libraries. |
| PostgreSQL connection refused | Check the container is running with `docker ps`, and that `DATABASE_URL` matches `docker-compose.yml`. |
| CORS errors in the browser console | Use the Vite dev server at http://localhost:5173 (it proxies requests), and make sure `CORS_ORIGINS` in `backend/.env` matches that URL. |

## Production notes

This starter is set up for development. Before deploying:

- Run Flask with a production server such as Gunicorn (`gunicorn "app:create_app()"`) instead of `debug=True`.
- Build the frontend with `npm run build` and serve the `frontend/dist` folder from a web server or static host, then route `/api` to the backend.
- Set `DATABASE_URL` and `CORS_ORIGINS` through your host's environment settings, and use a managed or properly secured database.
