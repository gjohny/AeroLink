#Alert endpoints. Registered in create_app() with the /api prefix

#GET  /api/alerts               the logged-in user's alerts, newest first (add ?unread=1 for unread only)
#                               only alerts for flights on trips the user owns or was shared
#POST /api/alerts/<id>/read     mark one alert as read for this user
#POST /api/alerts/read-all      mark all of this user's alerts as read
#POST /api/flights              send in a flight record (this is where Alan's data can land)

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Alert, AlertRead
from ..trip_sharing import current_user
from .checker import ingest_flight
from .flight_plan import alert_for_user, read_alert_ids, visible_alerts_query

alerts_bp = Blueprint("alerts", __name__, url_prefix = "/api")


@alerts_bp.get("/alerts")
def list_alerts():
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    alerts = visible_alerts_query(user).all()

    alert_ids = []
    for a in alerts:
        alert_ids.append(a.id)
    read_ids = read_alert_ids(user, alert_ids)

    alert_list = []
    for a in alerts:
        if request.args.get("unread") == "1" and a.id in read_ids:
            continue
        alert_list.append(alert_for_user(a, read_ids))

    return jsonify(alert_list)


@alerts_bp.post("/alerts/<int:alert_id>/read")
def mark_read(alert_id):
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    #Only alerts the user can see
    alert = visible_alerts_query(user).filter(Alert.id == alert_id).first()
    if alert is None:
        return jsonify(error = "Alert not found."), 404

    if alert.id not in read_alert_ids(user, [alert.id]):
        db.session.add(AlertRead(alert_id = alert.id, user_id = user.id))
        db.session.commit()

    return jsonify(alert_for_user(alert, {alert.id}))


@alerts_bp.post("/alerts/read-all")
def mark_all_read():
    user = current_user()
    if not user:
        return jsonify(error = "Not authenticated."), 401

    alerts = visible_alerts_query(user).all()

    alert_ids = []
    for a in alerts:
        alert_ids.append(a.id)
    read_ids = read_alert_ids(user, alert_ids)

    updated = 0
    for alert_id in alert_ids:
        if alert_id not in read_ids:
            db.session.add(AlertRead(alert_id = alert_id, user_id = user.id))
            updated += 1
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
        return jsonify(error = str(err)), 400

    new_alerts = []
    for a in created:
        new_alerts.append(a.to_dict())
    
    return jsonify(new_alerts = new_alerts), 201
