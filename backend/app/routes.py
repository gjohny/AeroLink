from flask import Blueprint, jsonify, request
from sqlalchemy import text

from .extensions import db
from .models import Task

api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/health")
def health():
    """Confirms the API is up and can reach the database."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok", database="connected")
    except Exception as exc:  # noqa: BLE001
        return jsonify(status="error", database=str(exc)), 500


@api.get("/tasks")
def list_tasks():
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tasks])


@api.post("/tasks")
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="Title is required."), 400

    task = Task(title=title[:200])
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201


@api.patch("/tasks/<int:task_id>")
def update_task(task_id):
    task = db.get_or_404(Task, task_id)
    data = request.get_json(silent=True) or {}

    if "done" in data:
        task.done = bool(data["done"])
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify(error="Title cannot be empty."), 400
        task.title = title[:200]

    db.session.commit()
    return jsonify(task.to_dict())


@api.delete("/tasks/<int:task_id>")
def delete_task(task_id):
    task = db.get_or_404(Task, task_id)
    db.session.delete(task)
    db.session.commit()
    return "", 204
