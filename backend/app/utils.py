"""Shared API validation, authorization, and serialization helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from typing import Any, Callable
from urllib.parse import urlparse

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from .extensions import db
from .models import User


MONEY_QUANTUM = Decimal("0.01")
# These limits match the signed INTEGER and NUMERIC(12, 2) columns in the
# operational schema.  Validating them before SQLAlchemy binds a value keeps
# malformed or impractically large requests from surfacing as database 500s.
MAX_DATABASE_INTEGER = 2_147_483_647
MAX_DATABASE_MONEY = Decimal("9999999999.99")


class APIError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "validation_error", details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


def error_response(error: APIError):
    payload: dict[str, Any] = {"error": {"code": error.code, "message": error.message}}
    if error.details is not None:
        payload["error"]["details"] = error.details
    return jsonify(payload), error.status_code


def role_required(*roles: str) -> Callable:
    """Require a valid JWT and one of the listed business roles."""
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            verify_jwt_in_request()
            user = current_user()
            if not user.is_active:
                raise APIError("Your account has been deactivated.", 403, "account_inactive")
            if user.role not in roles:
                raise APIError("You do not have permission for this action.", 403, "forbidden")
            return view(*args, **kwargs)
        return wrapped
    return decorator


def current_user() -> User:
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity)) if identity else None
    if not user:
        raise APIError("The account for this token no longer exists.", 401, "invalid_token")
    return user


def payload(request) -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("A JSON object request body is required.", 400, "invalid_json")
    return data


def required_string(data: dict[str, Any], field: str, *, max_length: int | None = None) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise APIError(f"{field.replace('_', ' ').capitalize()} is required.", details={field: "required"})
    value = value.strip()
    if max_length and len(value) > max_length:
        raise APIError(f"{field.replace('_', ' ').capitalize()} is too long.", details={field: f"max {max_length} characters"})
    return value


def optional_string(data: dict[str, Any], field: str, *, max_length: int | None = None) -> str | None:
    if field not in data or data[field] in (None, ""):
        return None
    value = data[field]
    if not isinstance(value, str):
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be text.", details={field: "must be text"})
    value = value.strip()
    if max_length and len(value) > max_length:
        raise APIError(f"{field.replace('_', ' ').capitalize()} is too long.", details={field: f"max {max_length} characters"})
    return value or None


def optional_http_url(data: dict[str, Any], field: str, *, max_length: int = 500) -> str | None:
    """Accept a removable public image URL without accepting inline or local data."""
    value = optional_string(data, field, max_length=max_length)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise APIError(
            f"{field.replace('_', ' ').capitalize()} must be a valid HTTP(S) URL.",
            details={field: "valid http(s) URL required"},
        )
    if parsed.username or parsed.password:
        raise APIError(
            f"{field.replace('_', ' ').capitalize()} must not include credentials.",
            details={field: "credentials are not allowed"},
        )
    return value


def as_decimal(
    value: Any,
    field: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be a valid amount.", details={field: "invalid number"})
    if not amount.is_finite():
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be a valid amount.", details={field: "invalid number"})
    if minimum is not None and amount < minimum:
        raise APIError(f"{field.replace('_', ' ').capitalize()} is below the allowed minimum.", details={field: f"minimum {minimum}"})
    if maximum is not None and amount > maximum:
        raise APIError(f"{field.replace('_', ' ').capitalize()} is above the allowed maximum.", details={field: f"maximum {maximum}"})
    return amount


def as_int(
    value: Any,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be a whole number.", details={field: "invalid integer"})
    try:
        decimal_value = Decimal(str(value))
        if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
            raise ValueError
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be a whole number.", details={field: "invalid integer"})
    # Compare as Decimal before converting to int.  This avoids constructing a
    # huge Python integer for an out-of-range API value.
    if minimum is not None and decimal_value < minimum:
        raise APIError(f"{field.replace('_', ' ').capitalize()} is below the allowed minimum.", details={field: f"minimum {minimum}"})
    if maximum is not None and decimal_value > maximum:
        raise APIError(f"{field.replace('_', ' ').capitalize()} is above the allowed maximum.", details={field: f"maximum {maximum}"})
    number = int(decimal_value)
    return number


def as_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be true or false.", details={field: "invalid boolean"})
    return value


def as_datetime(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be ISO-8601 text.", details={field: "invalid datetime"})
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise APIError(f"{field.replace('_', ' ').capitalize()} must be ISO-8601 text.", details={field: "invalid datetime"})
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise APIError(
            f"{field.replace('_', ' ').capitalize()} must include a timezone offset.",
            details={field: "timezone offset required"},
        )
    return parsed.astimezone(timezone.utc)


def page_args(request) -> tuple[int, int]:
    page = as_int(request.args.get("page", 1), "page", minimum=1, maximum=MAX_DATABASE_INTEGER)
    per_page = as_int(request.args.get("per_page", 20), "per_page", minimum=1, maximum=MAX_DATABASE_INTEGER)
    return page, min(per_page, 100)


def paginated(query, page: int, per_page: int, serializer: Callable[[Any], dict]) -> dict:
    result = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "data": [serializer(item) for item in result.items],
        "meta": {
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        },
    }
