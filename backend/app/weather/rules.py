"""Explainable prototype heuristics, not operational aviation limits.

Inspired by Southwest Weather Score (MIT); see THIRD_PARTY_NOTICES.md.
All scoring uses Celsius, mm/hour rain, cm/hour snow, metres visibility,
km/hour wind. Missing observations remain unknown rather than zero.
"""
from math import isfinite

VERSION = "weather-rules-v1"
DEFAULT_THRESHOLDS = {
    "rain_moderate": 2.5, "rain_high": 7.5, "snow_high": 1.0,
    "visibility_moderate": 5000, "visibility_high": 1000,
    "wind_moderate": 35, "wind_high": 50, "gust_moderate": 50, "gust_high": 70,
}
VARIABLES = ("temperature_2m", "precipitation_probability", "rain", "snowfall",
             "weather_code", "visibility", "wind_speed_10m", "wind_gusts_10m")
RISK_VARIABLES = tuple(v for v in VARIABLES if v not in ("temperature_2m", "precipitation_probability"))
RANK = {"unknown": -1, "low": 0, "moderate": 1, "high": 2}


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def assess_hour(values, thresholds=None):
    cfg = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    missing = [key for key in VARIABLES if not numeric(values.get(key))]
    def value(key):
        return values.get(key) if numeric(values.get(key)) else None
    code, rain, snow = value("weather_code"), value("rain"), value("snowfall")
    visibility, wind, gust = value("visibility"), value("wind_speed_10m"), value("wind_gusts_10m")
    hazards = []
    def add(kind, level, reason):
        hazards.append({"type": kind, "severity": level, "reason": reason,
                        "points": 40 if kind == "thunderstorm" else 35 if level == "high" else 15})
    if code in (95, 96, 99):
        add("thunderstorm", "high", "Thunderstorms are forecast; flights and driving may be disrupted.")
    if code in (65, 82) or (rain is not None and rain >= cfg["rain_high"]):
        add("rain", "high", "Heavy rain may reduce visibility and affect travel.")
    elif rain is not None and rain >= cfg["rain_moderate"]:
        add("rain", "moderate", "Rain may slow driving and affect airport operations.")
    if code in (75, 86) or (snow is not None and snow >= cfg["snow_high"]):
        add("snow", "high", "Heavy snowfall may affect roads and airport operations.")
    elif code in (71, 73, 77, 85) or (snow is not None and snow > 0):
        add("snow", "moderate", "Snow is forecast; allow for slower travel and possible deicing.")
    if code in (56, 57, 66, 67):
        add("freezing_precipitation", "high", "Freezing precipitation may create icy surfaces.")
    if visibility is not None and visibility < cfg["visibility_high"]:
        add("visibility", "high", f"Visibility below {cfg['visibility_high'] / 1000:g} km may affect flights and driving.")
    elif code in (45, 48) or (visibility is not None and visibility < cfg["visibility_moderate"]):
        add("visibility", "moderate", "Fog or reduced visibility may affect travel.")
    if (wind is not None and wind >= cfg["wind_high"]) or (gust is not None and gust >= cfg["gust_high"]):
        add("wind", "high", "Strong winds or gusts may affect flights and exposed roads.")
    elif (wind is not None and wind >= cfg["wind_moderate"]) or (gust is not None and gust >= cfg["gust_moderate"]):
        add("wind", "moderate", "Elevated winds or gusts may affect travel.")
    all_missing = all(key in missing for key in RISK_VARIABLES)
    return {"score": None if all_missing else min(100, sum(h["points"] for h in hazards)),
            "severity": max((h["severity"] for h in hazards), key=RANK.get, default="unknown" if all_missing else "low"),
            "hazards": hazards, "missing_variables": missing,
            "complete": not any(key in missing for key in RISK_VARIABLES), "rules_version": VERSION}


def summarize(rows):
    usable = [r for r in rows if r.get("score") is not None]
    hazards = {}
    for row in usable:
        for hazard in row["hazards"]:
            old = hazards.get(hazard["type"])
            if old is None or RANK[hazard["severity"]] > RANK[old["severity"]]:
                hazards[hazard["type"]] = hazard
    return {"score": max((r["score"] for r in usable), default=None),
            "severity": max((r["severity"] for r in usable), key=RANK.get, default="unknown"),
            "hazards": list(hazards.values()), "hours_assessed": len(usable),
            "complete": bool(rows) and all(r.get("complete", False) for r in rows)}
