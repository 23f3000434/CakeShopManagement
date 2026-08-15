"""Environment-based configuration for the Cake Shop application."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.pool import NullPool


BASE_DIR = Path(__file__).resolve().parent


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _cookie_samesite() -> str:
    """Normalise the spelling Flask/Werkzeug expects while retaining invalid input."""
    value = os.getenv("JWT_COOKIE_SAMESITE", "Lax").strip().lower()
    return {"lax": "Lax", "strict": "Strict", "none": "None"}.get(value, value)


def normalise_database_url(database_url: str | None) -> str:
    """Return a SQLAlchemy URL that works with psycopg and Aiven Postgres."""
    if not database_url:
        return f"sqlite:///{BASE_DIR / 'cake_shop.db'}"

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _with_ssl_options(database_url: str) -> str:
    """Add optional certificate settings without exposing secrets in source code."""
    if not database_url.startswith("postgresql"):
        return database_url

    sslmode = os.getenv("DB_SSLMODE")
    sslrootcert = os.getenv("DB_SSLROOTCERT")
    if not sslmode and not sslrootcert:
        return database_url

    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if sslmode:
        query["sslmode"] = sslmode
    if sslrootcert:
        query["sslrootcert"] = sslrootcert
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class Config:
    ENVIRONMENT = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).strip().lower()
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-jwt-change-me")
    SQLALCHEMY_DATABASE_URI = _with_ssl_options(normalise_database_url(os.getenv("DATABASE_URL")))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql") and os.getenv("DB_POOL_MODE") == "transaction":
        # Supabase's transaction pooler owns pooling. Psycopg's automatic
        # prepared statements cannot be reused across its backend connections.
        SQLALCHEMY_ENGINE_OPTIONS = {
            "poolclass": NullPool,
            "pool_pre_ping": True,
            "connect_args": {"prepare_threshold": None, "connect_timeout": 10},
        }

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int_env("ACCESS_TOKEN_MINUTES", 30))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int_env("REFRESH_TOKEN_DAYS", 14))
    # Access tokens travel in the Authorization header; refresh tokens are
    # rotated in an HTTP-only cookie so React never persists them in storage.
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_HEADER_TYPE = "Bearer"
    JWT_COOKIE_SECURE = _bool_env("JWT_COOKIE_SECURE", False)
    JWT_COOKIE_SAMESITE = _cookie_samesite()
    JWT_COOKIE_CSRF_PROTECT = True
    # Logout also needs the refresh family id to revoke the complete session.
    JWT_REFRESH_COOKIE_PATH = "/api/auth/"
    JWT_ACCESS_COOKIE_PATH = "/api/"

    CORS_ORIGINS = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()
    )
    SHOP_TIMEZONE = os.getenv("SHOP_TIMEZONE", "Asia/Kolkata")

    # Fixed credentials for the explicitly local-only `seed-local-admin` CLI.
    # The command itself refuses every non-development environment and every
    # non-SQLite database, so these values can never provision a deployed shop.
    LOCAL_DEVELOPMENT_ADMIN_NAME = "Butterlane Local Admin"
    LOCAL_DEVELOPMENT_ADMIN_EMAIL = "admin@butterlane.local"
    LOCAL_DEVELOPMENT_ADMIN_PASSWORD = "ButterlaneLocal2026!"

    JSON_SORT_KEYS = False

    @staticmethod
    def validate_runtime(config: dict) -> None:
        """Reject insecure deployed startup instead of silently degrading it."""
        environment = config.get("ENVIRONMENT")
        if config.get("TESTING") or environment == "development":
            return
        if environment not in {"staging", "production"}:
            raise RuntimeError("APP_ENV must be development, staging, or production")

        problems: list[str] = []
        for name in ("SECRET_KEY", "JWT_SECRET_KEY"):
            value = config.get(name, "")
            if value in {"development-only-change-me", "development-jwt-change-me"} or len(value) < 32:
                problems.append(f"{name} must be a unique value of at least 32 characters")
        if not os.getenv("DATABASE_URL"):
            problems.append("DATABASE_URL must point to the managed PostgreSQL database")
        if not str(config.get("SQLALCHEMY_DATABASE_URI", "")).startswith("postgresql"):
            problems.append("production requires PostgreSQL, not the SQLite fallback")
        sslmode = os.getenv("DB_SSLMODE", "").strip().lower()
        sslrootcert = os.getenv("DB_SSLROOTCERT", "").strip()
        if sslmode and sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            problems.append("DB_SSLMODE must be a valid SSL mode such as require, verify-ca, or verify-full")
        if sslmode == "verify-full" and not sslrootcert:
            problems.append("DB_SSLROOTCERT is required when DB_SSLMODE is verify-full")
        if not config.get("JWT_COOKIE_SECURE"):
            problems.append("JWT_COOKIE_SECURE=true is required over HTTPS")
        if config.get("JWT_COOKIE_SAMESITE") not in {"Lax", "Strict", "None"}:
            problems.append("JWT_COOKIE_SAMESITE must be Lax, Strict, or None")

        cors_origins = config.get("CORS_ORIGINS", ())
        if "*" in cors_origins:
            problems.append("CORS_ORIGINS must list explicit trusted origins when credentials are enabled")
        for origin in cors_origins:
            try:
                parsed = urlsplit(origin)
                _ = parsed.port  # Force malformed port values to be rejected.
                valid_origin = (
                    parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and not parsed.username
                    and not parsed.password
                    and not parsed.path
                    and not parsed.query
                    and not parsed.fragment
                )
            except ValueError:
                valid_origin = False
            if not valid_origin:
                problems.append("CORS_ORIGINS entries must be explicit HTTPS origins without paths")
                break
        try:
            ZoneInfo(config.get("SHOP_TIMEZONE", ""))
        except ZoneInfoNotFoundError:
            problems.append("SHOP_TIMEZONE must be a valid IANA timezone such as Asia/Kolkata")
        if problems:
            raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
