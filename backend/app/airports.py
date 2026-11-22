"""HTTP endpoints for the locally imported OurAirports data."""

import re

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from .extensions import db
from .models import Airport


AIRPORT_CODE = re.compile(r"^[A-Z]{3,4}$")
airports_api = Blueprint("airports_api", __name__, url_prefix="/api/airports")


def airport_to_dict(airport):
    return {
        "iata_code": airport.iata_code,
        "icao_code": airport.icao_code,
        "name": airport.name,
        "city": airport.municipality,
        "country": airport.iso_country,
        "region": airport.iso_region,
        "type": airport.type,
        "latitude": airport.latitude_deg,
        "longitude": airport.longitude_deg,
        "scheduled_service": bool(airport.scheduled_service),
    }


def lookup_airports(codes):
    """One SQL query for all flight departure/arrival codes."""
    codes = {code.strip().upper() for code in codes if isinstance(code, str) and code.strip()}
    if not codes:
        return {}
    found = db.session.execute(
        db.select(Airport).where(
            or_(Airport.iata_code.in_(codes), Airport.icao_code.in_(codes))
        )
    ).scalars().all()
    by_code = {}
    for airport in found:
        by_code[airport.iata_code] = airport_to_dict(airport)
        if airport.icao_code:
            by_code[airport.icao_code] = airport_to_dict(airport)
    return by_code


@airports_api.get("")
@airports_api.get("/")
def list_airports():
    """GET /api/airports?q=Houston&country=US&limit=10"""
    query = (request.args.get("q") or request.args.get("search") or "").strip()
    city = (request.args.get("city") or "").strip()
    code = (request.args.get("code") or "").strip().upper()
    country = (request.args.get("country") or "").strip().upper()

    if len(query) > 100 or len(city) > 100:
        return jsonify(error="Search text is too long (max 100 characters)."), 400
    if code and not AIRPORT_CODE.fullmatch(code):
        return jsonify(error="Airport code must be 3-4 letters."), 400
    if country and not re.fullmatch(r"[A-Z]{2}", country):
        return jsonify(error="Country must be a two-letter country code."), 400
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        return jsonify(error="limit must be a number from 1 to 100."), 400
    if not 1 <= limit <= 100:
        return jsonify(error="limit must be a number from 1 to 100."), 400

    stmt = db.select(Airport)
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(or_(
            Airport.name.ilike(pattern), Airport.municipality.ilike(pattern),
            Airport.iata_code.ilike(pattern), Airport.icao_code.ilike(pattern),
        ))
    if city:
        stmt = stmt.where(Airport.municipality.ilike(f"%{city}%"))
    if code:
        stmt = stmt.where(or_(Airport.iata_code == code, Airport.icao_code == code))
    if country:
        stmt = stmt.where(Airport.iso_country == country)
    stmt = stmt.order_by(Airport.scheduled_service.desc(), Airport.name, Airport.iata_code).limit(limit)
    airports = db.session.execute(stmt).scalars().all()
    return jsonify(airports=[airport_to_dict(a) for a in airports], count=len(airports))


@airports_api.get("/<string:code>")
def get_airport(code):
    code = code.strip().upper()
    if not AIRPORT_CODE.fullmatch(code):
        return jsonify(error="Airport code must be 3-4 letters."), 400
    airport = db.session.execute(
        db.select(Airport).where(or_(Airport.iata_code == code, Airport.icao_code == code))
    ).scalar_one_or_none()
    if not airport:
        return jsonify(error="Airport not found in the local database."), 404
    return jsonify(airport=airport_to_dict(airport))
