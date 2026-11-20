#Flag rules

#Each rule is a plain function: rule(old, new, cfg) -> alert dict or None
#  old : the previously stored flight record (dict) or None if the flight is new
#  new : the incoming flight record (dict)
#  cfg : the config class, so thresholds come from config.py

#Records use datetime objects (naive UTC) for the departure and arrival times
#An alert dict has: type, message, detail, dedupe_key, old_value, new_value
#The dedupe_key lets the checker skip an alert it already created for the same event
#old_value/new_value are what changed (a time as ISO 8601 UTC, or a gate), shown crossed out on the Flight Plan page

#To add a rule (for example road closures later), write one function and add it to RULES


def _minutes_between(start, end):
    return int((end - start).total_seconds() // 60)


def _fmt(moment):
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _iso(moment):
    return moment.isoformat() + "Z"


def check_delay(old, new, cfg):
    if new["status"] == "cancelled":
        return None
    delay = _minutes_between(new["scheduled_departure"], new["estimated_departure"])

    if delay < cfg.DELAY_THRESHOLD_MINUTES:
        return None
    
    return {"type": "delay", "message": f"Flight {new['flight_number']} is delayed by {delay} minutes", "detail": (f"Scheduled {_fmt(new['scheduled_departure'])}, now expected {_fmt(new['estimated_departure'])}"), "dedupe_key": str(delay), "old_value": _iso(new["scheduled_departure"]), "new_value": _iso(new["estimated_departure"])}


def check_arrival_delay(old, new, cfg):
    if new["status"] == "cancelled":
        return None

    if not new.get("scheduled_arrival") or not new.get("estimated_arrival"):
        return None

    delay = _minutes_between(new["scheduled_arrival"], new["estimated_arrival"])

    if delay < cfg.DELAY_THRESHOLD_MINUTES:
        return None

    return {"type": "arrival_delay", "message": f"Flight {new['flight_number']} will arrive {delay} minutes late", "detail": f"Scheduled arrival {_fmt(new['scheduled_arrival'])}, now expected {_fmt(new['estimated_arrival'])}", "dedupe_key": str(delay), "old_value": _iso(new["scheduled_arrival"]), "new_value": _iso(new["estimated_arrival"])}


def check_gate_change(old, new, cfg):
    if old is None or not old.get("gate") or not new.get("gate"):
        return None
    
    if old["gate"] == new["gate"]:
        return None
    
    return {"type": "gate_change", "message": f"Flight {new['flight_number']} moved from gate {old['gate']} to gate {new['gate']}", "detail": f"Previous gate {old['gate']}, new gate {new['gate']}", "dedupe_key": f"{old['gate']}->{new['gate']}", "old_value": old["gate"], "new_value": new["gate"]}


def check_arrival_gate_change(old, new, cfg):
    if old is None or not old.get("arrival_gate") or not new.get("arrival_gate"):
        return None

    if old["arrival_gate"] == new["arrival_gate"]:
        return None

    return {"type": "arrival_gate_change", "message": f"Flight {new['flight_number']} will now arrive at gate {new['arrival_gate']}", "detail": f"Previous arrival gate {old['arrival_gate']}, new arrival gate {new['arrival_gate']}", "dedupe_key": f"{old['arrival_gate']}->{new['arrival_gate']}", "old_value": old["arrival_gate"], "new_value": new["arrival_gate"]}


def check_cancellation(old, new, cfg):
    if new["status"] != "cancelled":
        return None
    
    if old is not None and old["status"] == "cancelled":
        return None
    
    return {"type": "cancellation", "message": f"Flight {new['flight_number']} was cancelled", "detail": f"Scheduled departure was {_fmt(new['scheduled_departure'])}", "dedupe_key": "cancelled", "old_value": old["status"] if old else None, "new_value": "cancelled"}


RULES = [check_delay, check_arrival_delay, check_gate_change, check_arrival_gate_change, check_cancellation]


def run_rules(old, new, cfg):
    alerts = []
    for rule in RULES:
        alert = rule(old, new, cfg)
        if alert:
            alerts.append(alert)

    return alerts
