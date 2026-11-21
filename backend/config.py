import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    SECRET_KEY = os.environ["SECRET_KEY"]
    AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY", "")
    AIRLABS_TIMEOUT = float(os.getenv("AIRLABS_TIMEOUT", "8"))
    FLIGHT_CACHE_TTL_SECONDS = int(os.getenv("FLIGHT_CACHE_TTL_SECONDS", "300"))
    FLIGHT_DELAY_THRESHOLD_MINUTES = int(os.getenv("FLIGHT_DELAY_THRESHOLD_MINUTES", "20"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
