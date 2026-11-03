#Fake flight records for testing before the real data is ready

#Each scenario is a list of updates for one flight, in the order they would arrive
#Load them all into your local database from the backend folder with: python -m app.alerts.mock_data


NORMAL = [{"flight_number": "AA100", "scheduled_departure": "2026-11-02T09:00:00Z", "estimated_departure": "2026-11-02T09:00:00Z", "status": "scheduled", "gate": "A4"},
    {"flight_number": "AA100", "scheduled_departure": "2026-11-02T09:00:00Z", "estimated_departure": "2026-11-02T09:05:00Z", "status": "scheduled", "gate": "A4"}]

DELAYED = [{"flight_number": "UA200", "scheduled_departure": "2026-11-02T15:10:00Z", "estimated_departure": "2026-11-02T15:10:00Z", "status": "scheduled", "gate": "B12"},
    {"flight_number": "UA200", "scheduled_departure": "2026-11-02T15:10:00Z", "estimated_departure": "2026-11-02T15:40:00Z", "status": "delayed", "gate": "B12"}]

GATE_CHANGED = [{"flight_number": "DL300", "scheduled_departure": "2026-11-02T18:30:00Z", "estimated_departure": "2026-11-02T18:30:00Z", "status": "scheduled", "gate": "C3"},
    {"flight_number": "DL300", "scheduled_departure": "2026-11-02T18:30:00Z", "estimated_departure": "2026-11-02T18:30:00Z", "status": "scheduled", "gate": "C9"}]

CANCELLED = [{"flight_number": "SW400", "scheduled_departure": "2026-11-03T07:45:00Z", "estimated_departure": "2026-11-03T07:45:00Z", "status": "scheduled", "gate": "D2"},
    {"flight_number": "SW400", "scheduled_departure": "2026-11-03T07:45:00Z", "estimated_departure": "2026-11-03T07:45:00Z", "status": "cancelled", "gate": "D2"}]

ALL_SCENARIOS = {"normal": NORMAL, "delayed": DELAYED, "gate_changed": GATE_CHANGED, "cancelled": CANCELLED}


if __name__ == "__main__":
    from app import create_app
    from app.alerts.checker import ingest_flight

    app = create_app()
    with app.app_context():
        for name, updates in ALL_SCENARIOS.items():
            for record in updates:
                for alert in ingest_flight(record):
                    print(f"[{name}] {alert.message}")
                    
    print("Mock data loaded.")
