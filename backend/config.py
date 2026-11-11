import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    SECRET_KEY = os.environ["SECRET_KEY"]
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"

    # No-key, noncommercial prototype providers; keep endpoints configurable.
    WEATHER_FORECAST_URL = os.getenv("WEATHER_FORECAST_URL", "https://api.open-meteo.com")
    WEATHER_GEOCODING_URL = os.getenv("WEATHER_GEOCODING_URL", "https://geocoding-api.open-meteo.com")
    WEATHER_ROUTING_URL = os.getenv("WEATHER_ROUTING_URL", "https://router.project-osrm.org")
    WEATHER_CACHE_SECONDS = 1800
    WEATHER_WORKER_INTERVAL_SECONDS = 300
    WEATHER_MODEL_MANIFEST = os.getenv("WEATHER_MODEL_MANIFEST")
    WEATHER_THRESHOLDS = {}
