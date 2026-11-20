#Fake flight records for testing before the real data is ready

#Each scenario is a list of updates for one flight, in the order they would arrive
#Load the fixed scenarios below (used by the tests) from the backend folder with: python -m app.alerts.mock_data

#To see the Flight Plan page change, add a flight to a trip on the site, then play a demo for that same flight and date:
#    python -m app.alerts.mock_data AA100 2026-12-01 delayed
#Demos: on_time, delayed, gate_change, arrival_changes, cancelled, busy (several changes in a row)


NORMAL = [{"flight_number": "AA100", "scheduled_departure": "2026-11-02T09:00:00Z", "estimated_departure": "2026-11-02T09:00:00Z", "status": "scheduled", "gate": "A4"},
    {"flight_number": "AA100", "scheduled_departure": "2026-11-02T09:00:00Z", "estimated_departure": "2026-11-02T09:05:00Z", "status": "scheduled", "gate": "A4"}]

DELAYED = [{"flight_number": "UA200", "scheduled_departure": "2026-11-02T15:10:00Z", "estimated_departure": "2026-11-02T15:10:00Z", "status": "scheduled", "gate": "B12"},
    {"flight_number": "UA200", "scheduled_departure": "2026-11-02T15:10:00Z", "estimated_departure": "2026-11-02T15:40:00Z", "status": "delayed", "gate": "B12"}]

GATE_CHANGED = [{"flight_number": "DL300", "scheduled_departure": "2026-11-02T18:30:00Z", "estimated_departure": "2026-11-02T18:30:00Z", "status": "scheduled", "gate": "C3"},
    {"flight_number": "DL300", "scheduled_departure": "2026-11-02T18:30:00Z", "estimated_departure": "2026-11-02T18:30:00Z", "status": "scheduled", "gate": "C9"}]

CANCELLED = [{"flight_number": "SW400", "scheduled_departure": "2026-11-03T07:45:00Z", "estimated_departure": "2026-11-03T07:45:00Z", "status": "scheduled", "gate": "D2"},
    {"flight_number": "SW400", "scheduled_departure": "2026-11-03T07:45:00Z", "estimated_departure": "2026-11-03T07:45:00Z", "status": "cancelled", "gate": "D2"}]

ALL_SCENARIOS = {"normal": NORMAL, "delayed": DELAYED, "gate_changed": GATE_CHANGED, "cancelled": CANCELLED}


def demo_records(flight_number, flight_date, name):
    #Build a demo scenario for any flight number and date, with departure and arrival details
    from datetime import date, datetime, timedelta

    day = date.fromisoformat(flight_date)
    departs = datetime(day.year, day.month, day.day, 15, 10)
    arrives = departs + timedelta(hours = 9, minutes = 20)

    def at(moment):
        return moment.isoformat() + "Z"

    base = {"flight_number": flight_number, "flight_date": flight_date, "airline": "Demo Airlines", "status": "scheduled", "departure_airport": "ORD", "arrival_airport": "FCO", "scheduled_departure": at(departs), "estimated_departure": at(departs), "departure_terminal": "3", "gate": "B12", "scheduled_arrival": at(arrives), "estimated_arrival": at(arrives), "arrival_terminal": "1", "arrival_gate": "E4"}

    late = dict(base, status = "delayed", estimated_departure = at(departs + timedelta(minutes = 55)), estimated_arrival = at(arrives + timedelta(minutes = 45)))

    demos = {"on_time": [base],
        "delayed": [base, late],
        "gate_change": [base, dict(base, gate = "C4")],
        "arrival_changes": [base, dict(base, estimated_arrival = at(arrives + timedelta(minutes = 35)), arrival_gate = "D7")],
        "cancelled": [base, dict(base, status = "cancelled")],
        "busy": [base, dict(base, gate = "C4"), dict(late, gate = "C4"), dict(late, gate = "C4", arrival_gate = "D7")]}

    if name not in demos:
        raise ValueError(f"Unknown demo '{name}'. Choose one of: {', '.join(demos)}")

    return demos[name]


if __name__ == "__main__":
    import sys

    from app import create_app
    from app.alerts.checker import ingest_flight

    app = create_app()
    with app.app_context():
        if len(sys.argv) == 4:
            #python -m app.alerts.mock_data AA100 2026-12-01 delayed
            for record in demo_records(sys.argv[1].upper(), sys.argv[2], sys.argv[3]):
                for alert in ingest_flight(record):
                    print(f"[{sys.argv[3]}] {alert.message}")
        else:
            for name, updates in ALL_SCENARIOS.items():
                for record in updates:
                    for alert in ingest_flight(record):
                        print(f"[{name}] {alert.message}")

    print("Mock data loaded.")
