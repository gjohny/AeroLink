#Flag rules

#Each rule is a plain function: rule(old, new, cfg) -> alert dict or None
#  old : the previously stored flight record (dict) or None if the flight is new
#  new : the incoming flight record (dict)
#  cfg : the config class, so thresholds come from config.py

#Records use datetime objects (naive UTC) for the two departure times
#An alert dict has: type, message, detail, dedupe_key
#The dedupe_key lets the checker skip an alert it already created for the same event

#To add a rule (for example road closures later), write one function and add it to RULES


def _minutes_between(start, end):
    return int((end - start).total_seconds() // 60)


def _fmt(moment):
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def check_delay(old, new, cfg):
    if new["status"] == "cancelled":
        return None
    delay = _minutes_between(new["scheduled_departure"], new["estimated_departure"])

    if delay < cfg.DELAY_THRESHOLD_MINUTES:
        return None
    
    return {"type": "delay", "message": f"Flight {new['flight_number']} is delayed by {delay} minutes", "detail": (f"Scheduled {_fmt(new['scheduled_departure'])}, now expected {_fmt(new['estimated_departure'])}"), "dedupe_key": str(delay)}


def check_gate_change(old, new, cfg):
    if old is None or not old.get("gate") or not new.get("gate"):
        return None
    
    if old["gate"] == new["gate"]:
        return None
    
    return {"type": "gate_change", "message": f"Flight {new['flight_number']} moved from gate {old['gate']} to gate {new['gate']}", "detail": f"Previous gate {old['gate']}, new gate {new['gate']}", "dedupe_key": f"{old['gate']}->{new['gate']}"}


def check_cancellation(old, new, cfg):
    if new["status"] != "cancelled":
        return None
    
    if old is not None and old["status"] == "cancelled":
        return None
    
    return {"type": "cancellation", "message": f"Flight {new['flight_number']} was cancelled", "detail": f"Scheduled departure was {_fmt(new['scheduled_departure'])}", "dedupe_key": "cancelled"}


RULES = [check_delay, check_gate_change, check_cancellation]


def run_rules(old, new, cfg):
    alerts = []
    for rule in RULES:
        alert = rule(old, new, cfg)
        if alert:
            alerts.append(alert)

    return alerts
