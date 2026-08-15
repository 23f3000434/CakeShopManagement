"""Authentication endpoints and first-admin onboarding."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from .extensions import db
from .models import AuditLog, SessionBlocklist, TokenBlocklist, User, utc_now
from .utils import APIError, current_user, optional_string, payload, required_string, role_required


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _email(data: dict) -> str:
    email = required_string(data, "email", max_length=255).lower()
    if not EMAIL_PATTERN.match(email):
        raise APIError("Enter a valid email address.", details={"email": "invalid email"})
    return email


def _password(data: dict) -> str:
    value = required_string(data, "password", max_length=256)
    if len(value) < 10:
        raise APIError("Password must contain at least 10 characters.", details={"password": "minimum 10 characters"})
    return value


def _tokens_for(user: User, session_id: str | None = None) -> dict:
    claims = {
        "role": user.role,
        "name": user.full_name,
        "sid": session_id or str(uuid4()),
        "sv": user.session_version,
    }
    return {
        "access_token": create_access_token(identity=str(user.id), additional_claims=claims),
        "refresh_token": create_refresh_token(identity=str(user.id), additional_claims=claims),
    }


def _session_response(message: str, user: User, status_code: int = 200, session_id: str | None = None):
    """Return only the short-lived access token; rotate refresh via HTTP-only cookie."""
    tokens = _tokens_for(user, session_id)
    response = jsonify(
        {
            "message": message,
            "user": user.to_dict(),
            "access_token": tokens["access_token"],
        }
    )
    set_refresh_cookies(response, tokens["refresh_token"])
    return response, status_code


def _commit_auth(*, on_conflict: APIError | None = None) -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if on_conflict:
            raise on_conflict
        raise APIError("This record conflicts with existing data.", 409, "conflict")


def _flush_auth() -> None:
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise APIError("This record conflicts with existing data.", 409, "conflict")


def _revoke_token(token: dict, user_id: int) -> None:
    if not TokenBlocklist.query.filter_by(jti=token["jti"]).first():
        db.session.add(
            TokenBlocklist(
                jti=token["jti"],
                token_type=token["type"],
                user_id=user_id,
                expires_at=datetime.fromtimestamp(token["exp"], timezone.utc),
            )
        )


@auth_bp.post("/bootstrap")
def bootstrap_admin():
    """Create a local development owner once; deployed environments use the CLI."""
    if current_app.config["ENVIRONMENT"] != "development":
        raise APIError(
            "Account provisioning is disabled over HTTP outside local development. Run the protected create-admin release command instead.",
            403,
            "bootstrap_disabled",
        )
    if User.query.count() > 0:
        raise APIError("Initial admin setup has already been completed.", 409, "already_initialized")

    data = payload(request)
    user = User(
        full_name=required_string(data, "full_name", max_length=120),
        email=_email(data),
        role="admin",
    )
    user.set_password(_password(data))
    db.session.add(user)
    _commit_auth()
    return _session_response("Owner account created.", user, 201)


@auth_bp.get("/dev-credentials")
def dev_credentials():
    """Return local admin credentials for zero-friction local development testing."""
    if current_app.config.get("ENVIRONMENT") != "development":
        raise APIError("Development credentials are only available in development environment.", 403, "forbidden")
    return jsonify({
        "email": current_app.config.get("LOCAL_DEVELOPMENT_ADMIN_EMAIL", "admin@butterlane.local"),
        "password": current_app.config.get("LOCAL_DEVELOPMENT_ADMIN_PASSWORD", "ButterlaneLocal2026!"),
        "name": current_app.config.get("LOCAL_DEVELOPMENT_ADMIN_NAME", "Butterlane Local Admin"),
    })


@auth_bp.post("/login")
def login():
    data = payload(request)
    email = _email(data)
    password = required_string(data, "password", max_length=256)

    user = User.query.filter_by(email=email).first()
    if not user and current_app.config.get("ENVIRONMENT") == "development" and db.engine.dialect.name == "sqlite":
        seed_email = current_app.config.get("LOCAL_DEVELOPMENT_ADMIN_EMAIL", "").lower()
        seed_pass = current_app.config.get("LOCAL_DEVELOPMENT_ADMIN_PASSWORD", "")
        if email == seed_email and password == seed_pass and User.query.count() == 0:
            user = User(
                full_name=current_app.config.get("LOCAL_DEVELOPMENT_ADMIN_NAME", "Butterlane Local Admin"),
                email=seed_email,
                role="admin",
            )
            user.set_password(seed_pass)
            db.session.add(user)
            db.session.flush()
            db.session.add(
                AuditLog(
                    actor_user_id=user.id,
                    action="user.created",
                    entity_type="user",
                    entity_id=str(user.id),
                    details={"email": user.email, "role": "admin", "source": "local_development_auto_seed"},
                )
            )
            db.session.commit()

    if not user or not user.check_password(password):
        raise APIError("Email or password is incorrect.", 401, "invalid_credentials")
    if not user.is_active:
        raise APIError("Your account has been deactivated.", 403, "account_inactive")

    return _session_response("Signed in successfully.", user)


@auth_bp.post("/refresh")
@jwt_required(refresh=True, locations=["cookies"])
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.is_active:
        raise APIError("Your account is unavailable.", 401, "invalid_token")
    # Rotation limits the useful lifetime of a stolen refresh cookie.
    old_token = get_jwt()
    _revoke_token(old_token, user.id)
    _commit_auth(on_conflict=APIError("This refresh token has already been used.", 401, "token_revoked"))
    return _session_response("Session refreshed.", user, session_id=old_token.get("sid"))


@auth_bp.post("/logout")
@jwt_required(refresh=True, locations=["cookies"])
def logout():
    token = get_jwt()
    user_id = int(get_jwt_identity())
    session_id = token.get("sid")
    if session_id and not SessionBlocklist.query.filter_by(session_id=session_id).first():
        db.session.add(
            SessionBlocklist(
                session_id=session_id,
                user_id=user_id,
                expires_at=utc_now() + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"],
            )
        )
    else:
        _revoke_token(token, user_id)
    # A concurrent double-click can collide on the session id; either outcome
    # is an already-signed-out session, so return success rather than a 500.
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    response = jsonify({"message": "Signed out successfully."})
    unset_jwt_cookies(response)
    return response


@auth_bp.get("/me")
@jwt_required()
def me():
    return jsonify({"user": current_user().to_dict()})


@auth_bp.get("/users")
@role_required("admin")
def list_users():
    users = User.query.order_by(User.full_name.asc()).all()
    return jsonify({"data": [user.to_dict() for user in users]})


@auth_bp.post("/users")
@role_required("admin")
def create_user():
    data = payload(request)
    role = required_string(data, "role", max_length=20).lower()
    if role not in {"admin", "manager", "staff"}:
        raise APIError("Role must be admin, manager, or staff.", details={"role": "invalid role"})
    email = _email(data)
    if User.query.filter_by(email=email).first():
        raise APIError("A user already exists with this email.", 409, "duplicate_email")

    user = User(
        full_name=required_string(data, "full_name", max_length=120),
        email=email,
        role=role,
    )
    user.set_password(_password(data))
    db.session.add(user)
    _flush_auth()
    db.session.add(
        AuditLog(
            actor_user_id=current_user().id,
            action="user.created",
            entity_type="user",
            entity_id=str(user.id),
            details={"email": user.email, "role": user.role},
        )
    )
    _commit_auth()
    return jsonify({"data": user.to_dict()}), 201


@auth_bp.patch("/users/<int:user_id>")
@role_required("admin")
def update_user(user_id: int):
    user = db.session.execute(
        db.select(User).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none()
    if not user:
        raise APIError("User not found.", 404, "not_found")
    data = payload(request)
    actor = current_user()

    next_role = user.role
    next_is_active = user.is_active
    if "role" in data:
        next_role = required_string(data, "role", max_length=20).lower()
        if next_role not in {"admin", "manager", "staff"}:
            raise APIError("Role must be admin, manager, or staff.", details={"role": "invalid role"})
    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            raise APIError("is active must be true or false.", details={"is_active": "invalid boolean"})
        next_is_active = data["is_active"]
    if user.id == actor.id and not next_is_active:
        raise APIError("You cannot deactivate your own account.", 409, "self_deactivation")

    if user.role == "admin" and user.is_active and (next_role != "admin" or not next_is_active):
        active_admins = db.session.execute(
            db.select(User)
            .where(User.role == "admin", User.is_active.is_(True))
            .with_for_update()
        ).scalars().all()
        if len(active_admins) <= 1:
            raise APIError(
                "Keep at least one active administrator before changing this account.",
                409,
                "last_admin_protected",
            )

    changes: dict[str, object] = {}

    if "role" in data:
        user.role = next_role
        changes["role"] = next_role
    if "is_active" in data:
        user.is_active = next_is_active
        changes["is_active"] = next_is_active
        if not user.is_active:
            user.session_version += 1
    if "full_name" in data:
        user.full_name = required_string(data, "full_name", max_length=120)
        changes["full_name"] = user.full_name
    if "password" in data:
        user.set_password(_password(data))
        user.session_version += 1
        changes["password_changed"] = True

    if changes:
        db.session.add(
            AuditLog(
                actor_user_id=actor.id,
                action="user.updated",
                entity_type="user",
                entity_id=str(user.id),
                details=changes,
            )
        )
    _commit_auth()
    return jsonify({"data": user.to_dict()})
