# AeroLink Airport Database

The airport database stores basic airport information from [OurAirports](https://ourairports.com/data/) in SQLite. It includes airport codes, names, locations, and coordinates. No API connection is required for this setup.

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
python -m scripts.check_airports --city Houston --country US
```

## Run tests

```powershell
python -m unittest discover -s tests -v
```
