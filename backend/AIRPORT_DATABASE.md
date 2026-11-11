# AeroLink Airport Database

The airport database stores basic airport information from [OurAirports](https://ourairports.com/data/) in SQLite. It includes airport codes, names, locations, and coordinates. No API connection is required for this setup.

## Files

- `app/models.py` — Defines the `Airport` database model.
- `data/airports_cleaned.csv` — Cleaned airport data.
- `scripts/import_airports.py` — Imports airport data into SQLite.
- `scripts/check_airports.py` — Searches the local database.

## Setup

Open a terminal in the project's `backend` folder and run:

```powershell
python -m scripts.import_airports
```

This imports the cleaned data into `backend/instance/app.db`. Run the command again to refresh the airport records.

## Check the database

From the `backend` folder, run:

```powershell
python -m scripts.check_airports
python -m scripts.check_airports --code CLL
python -m scripts.check_airports --code TPE
python -m scripts.check_airports --city Houston --country US
```

## Run tests

```powershell
python -m unittest discover -s tests -v
```

The SQLite database file is not tracked by Git. After cloning the repository, run the import command to create it locally.

Airport API endpoints and frontend integration are not included in this setup.
