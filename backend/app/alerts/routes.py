#Alert endpoints. Registered in create_app() with the /api prefix

#GET  /api/alerts               list alerts, newest first (add ?unread=1 for unread only)
#POST /api/alerts/<id>/read     mark one alert as read
#POST /api/alerts/read-all      mark every alert as read
#POST /api/flights              send in a flight record (this is where Alan's data can land)

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Alert
from .checker import ingest_flight

alerts_bp = Blueprint("alerts", __name__, url_prefix = "/api")


@alerts_bp.get("/alerts")
def list_alerts():
    query = Alert.query
    if request.args.get("unread") == "1":
        query = query.filter_by(is_read = False)

    alerts = query.order_by(Alert.id.desc()).all()

    alert_list = []
    for a in alerts:
        alert_list.append(a.to_dict())

    return jsonify(alert_list)


@alerts_bp.post("/alerts/<int:alert_id>/read")
def mark_read(alert_id):
    alert = db.get_or_404(Alert, alert_id)
    alert.is_read = True
    db.session.commit()

    return jsonify(alert.to_dict())


@alerts_bp.post("/alerts/read-all")
def mark_all_read():
    updated = Alert.query.filter_by(is_read = False).update({"is_read": True})
    db.session.commit()

    return jsonify(updated = updated)


@alerts_bp.post("/flights")
def receive_flight():
    record = request.get_json(silent = True)

    if not record:
        return jsonify(error="Send a JSON flight record."), 400
    try:
        created = ingest_flight(record)
    except ValueError as err:
        return jsonify(erro = str(err)), 400

    new_alerts = []
    for a in created:
        new_alerts.append(a.to_dict())
    
    return jsonify(new_alerts = new_alerts), 201
