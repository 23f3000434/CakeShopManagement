from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

import app.resources as resources
from app import create_app
from app.extensions import db
from app.models import AuditLog, Payment, User


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "JWT_SECRET_KEY": "test-jwt-secret-that-is-longer-than-thirty-two-characters",
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def bootstrap(client):
    response = client.post(
        "/api/auth/bootstrap",
        json={"full_name": "Asha Owner", "email": "owner@butterlane.test", "password": "securepassword1"},
    )
    assert response.status_code == 201
    return response.get_json()


def auth_headers(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


def financial_headers(session, key):
    return {**auth_headers(session), "Idempotency-Key": key}


def test_bootstrap_is_single_use_and_health_is_public(client):
    assert client.get("/api/health").status_code == 200
    bootstrap(client)
    repeat = client.post(
        "/api/auth/bootstrap",
        json={"full_name": "Other", "email": "other@example.test", "password": "anotherpassword1"},
    )
    assert repeat.status_code == 409
    assert repeat.get_json()["error"]["code"] == "already_initialized"


def test_bootstrap_is_disabled_outside_local_development(app):
    app.config["ENVIRONMENT"] = "staging"
    response = app.test_client().post(
        "/api/auth/bootstrap",
        json={"full_name": "Other", "email": "other@example.test", "password": "anotherpassword1"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "bootstrap_disabled"


def test_seed_local_admin_creates_a_fixed_local_admin_once_and_preserves_it(app, client):
    runner = app.test_cli_runner()
    first = runner.invoke(args=["seed-local-admin"])
    assert first.exit_code == 0
    assert "Created local development administrator admin@butterlane.local." in first.output
    assert "ButterlaneLocal2026!" not in first.output

    sign_in = client.post(
        "/api/auth/login",
        json={"email": "admin@butterlane.local", "password": "ButterlaneLocal2026!"},
    )
    assert sign_in.status_code == 200
    assert sign_in.get_json()["user"]["role"] == "admin"

    with app.app_context():
        seeded = User.query.filter_by(email="admin@butterlane.local").one()
        assert seeded.full_name == "Butterlane Local Admin"
        assert seeded.role == "admin"
        assert seeded.is_active is True
        assert seeded.check_password("ButterlaneLocal2026!")
        assert AuditLog.query.filter_by(action="user.created").one().details["source"] == "local_development_seed"
        seeded.set_password("a-local-password-that-is-not-reset")
        db.session.commit()

    repeated = runner.invoke(args=["seed-local-admin"])
    assert repeated.exit_code == 0
    assert "local seed unchanged" in repeated.output
    with app.app_context():
        seeded = User.query.filter_by(email="admin@butterlane.local").one()
        assert seeded.check_password("a-local-password-that-is-not-reset")
        assert User.query.count() == 1


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_seed_local_admin_refuses_deployed_environment(app, environment):
    runner = app.test_cli_runner()
    app.config["ENVIRONMENT"] = environment
    refused = runner.invoke(args=["seed-local-admin"])
    assert refused.exit_code != 0
    assert "only with APP_ENV=development on a local SQLite database" in refused.output
    with app.app_context():
        assert User.query.count() == 0


def test_seed_local_admin_refuses_non_sqlite_and_retains_existing_admin(app, monkeypatch):
    runner = app.test_cli_runner()
    with app.app_context():
        monkeypatch.setattr(db.engine.dialect, "name", "postgresql")
    refused = runner.invoke(args=["seed-local-admin"])
    assert refused.exit_code != 0
    assert "only with APP_ENV=development on a local SQLite database" in refused.output

    monkeypatch.undo()
    app.config["ENVIRONMENT"] = "development"
    existing = User(full_name="Existing Admin", email="existing@butterlane.local", role="admin")
    existing.set_password("another-local-admin-password")
    with app.app_context():
        db.session.add(existing)
        db.session.commit()

    retained = runner.invoke(args=["seed-local-admin"])
    assert retained.exit_code == 0
    assert "existing@butterlane.local" in retained.output
    with app.app_context():
        assert User.query.count() == 1
        assert User.query.filter_by(email="admin@butterlane.local").first() is None


def test_secure_order_lifecycle_tracks_stock_payments_and_customer_metrics(client):
    session = bootstrap(client)
    headers = auth_headers(session)

    product_response = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": "RED-VELVET-6",
            "name": "Red Velvet Celebration Cake",
            "category": "Celebration Cakes",
            "unit_price": "1200.00",
            "cost_price": "470.00",
            "stock_quantity": 4,
            "reorder_level": 2,
        },
    )
    assert product_response.status_code == 201
    product = product_response.get_json()["data"]
    assert product["stock_quantity"] == 4

    customer_response = client.post(
        "/api/customers",
        headers=headers,
        json={"full_name": "Mira Kapoor", "phone": "+91 98765 43210"},
    )
    assert customer_response.status_code == 201
    customer = customer_response.get_json()["data"]

    order_response = client.post(
        "/api/orders",
        headers=headers,
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
            "discount_amount": "100",
            "tax_rate": "5",
            "notes": "Please add a handwritten birthday card.",
        },
    )
    assert order_response.status_code == 201
    order = order_response.get_json()["data"]
    assert order["status"] == "draft"
    assert order["subtotal"] == 2400.0
    assert order["total_amount"] == 2415.0

    # Catalogue edits may not directly change stock—the stock ledger must be used.
    invalid_stock_edit = client.patch(
        f"/api/products/{product['id']}", headers=headers, json={"stock_quantity": 99}
    )
    assert invalid_stock_edit.status_code == 409
    assert invalid_stock_edit.get_json()["error"]["code"] == "stock_adjustment_required"

    confirmed = client.post(
        f"/api/orders/{order['id']}/transition", headers=headers, json={"status": "confirmed", "version": order["version"]}
    )
    assert confirmed.status_code == 200
    order = confirmed.get_json()["data"]
    assert order["status"] == "confirmed"

    updated_product = client.get(f"/api/products/{product['id']}", headers=headers).get_json()["data"]
    assert updated_product["stock_quantity"] == 2

    payment = client.post(
        f"/api/orders/{order['id']}/payments",
        headers=financial_headers(session, "secure-lifecycle-payment"),
        json={"amount": "2415", "method": "upi", "provider_reference": "UPI-CAKE-42"},
    )
    assert payment.status_code == 201
    order = payment.get_json()["order"]
    assert order["payment_status"] == "paid"

    for target in ("in_progress", "ready", "completed"):
        next_response = client.post(
            f"/api/orders/{order['id']}/transition",
            headers=headers,
            json={"status": target, "version": order["version"]},
        )
        assert next_response.status_code == 200
        order = next_response.get_json()["data"]

    customer_after = client.get(f"/api/customers/{customer['id']}", headers=headers).get_json()["data"]
    assert customer_after["completed_order_count"] == 1
    assert customer_after["total_spent"] == 2415.0


def test_order_cancellation_restores_committed_stock(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    product = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "CHOC-8", "name": "Chocolate Cake", "unit_price": 900, "stock_quantity": 1},
    ).get_json()["data"]
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    ).get_json()["data"]

    confirmed = client.post(
        f"/api/orders/{order['id']}/transition", headers=headers, json={"status": "confirmed"}
    )
    assert confirmed.status_code == 200
    cancelled = client.post(
        f"/api/orders/{order['id']}/transition", headers=headers, json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200
    product_after = client.get(f"/api/products/{product['id']}", headers=headers).get_json()["data"]
    assert product_after["stock_quantity"] == 1


def test_logout_revokes_token(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    csrf_cookie = client.get_cookie("csrf_refresh_token")
    assert client.post("/api/auth/logout", headers={"X-CSRF-TOKEN": csrf_cookie.value}).status_code == 200
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "token_revoked"


def test_refresh_token_is_http_only_cookie_and_rotates(client):
    session = bootstrap(client)
    assert "refresh_token" not in session
    csrf_cookie = client.get_cookie("csrf_refresh_token")
    assert csrf_cookie is not None
    refreshed = client.post("/api/auth/refresh", headers={"X-CSRF-TOKEN": csrf_cookie.value})
    assert refreshed.status_code == 200
    assert refreshed.get_json()["access_token"]


def test_duplicate_lines_and_non_finite_money_are_rejected_safely(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    invalid_price = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "BAD-PRICE", "name": "Broken Cake", "unit_price": "NaN"},
    )
    assert invalid_price.status_code == 400

    product = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "LEMON-6", "name": "Lemon Cake", "unit_price": 600, "stock_quantity": 3},
    ).get_json()["data"]
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 2}, {"product_id": product["id"], "quantity": 2}]},
    ).get_json()["data"]
    confirmed = client.post(
        f"/api/orders/{order['id']}/transition", headers=headers, json={"status": "confirmed"}
    )
    assert confirmed.status_code == 409
    assert confirmed.get_json()["error"]["code"] == "insufficient_stock"
    stock = client.get(f"/api/products/{product['id']}", headers=headers).get_json()["data"]["stock_quantity"]
    assert stock == 3


def test_product_image_url_is_serialized_updated_and_must_be_a_public_url(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    original_url = "https://cdn.butterlane.test/cakes/red-velvet-6.webp"
    created = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": "IMAGE-6",
            "name": "Red Velvet Image Cake",
            "unit_price": 1200,
            "image_url": original_url,
        },
    )
    assert created.status_code == 201
    product = created.get_json()["data"]
    assert product["image_url"] == original_url

    replacement_url = "https://images.butterlane.test/catalogue/red-velvet-6.jpg?width=1200"
    updated = client.patch(
        f"/api/products/{product['id']}",
        headers=headers,
        json={"image_url": replacement_url},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["image_url"] == replacement_url

    invalid = client.patch(
        f"/api/products/{product['id']}",
        headers=headers,
        json={"image_url": "data:image/svg+xml,<svg></svg>"},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["details"]["image_url"] == "valid http(s) URL required"

    cleared = client.patch(f"/api/products/{product['id']}", headers=headers, json={"image_url": None})
    assert cleared.status_code == 200
    assert cleared.get_json()["data"]["image_url"] is None


def test_completion_requires_payment_and_cancelled_orders_can_refund(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    product = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "VANILLA-6", "name": "Vanilla Cake", "unit_price": 750, "stock_quantity": 2},
    ).get_json()["data"]
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    ).get_json()["data"]
    for status in ("confirmed", "in_progress", "ready"):
        response = client.post(f"/api/orders/{order['id']}/transition", headers=headers, json={"status": status})
        assert response.status_code == 200
        order = response.get_json()["data"]
    unpaid_complete = client.post(
        f"/api/orders/{order['id']}/transition", headers=headers, json={"status": "completed"}
    )
    assert unpaid_complete.status_code == 409
    assert unpaid_complete.get_json()["error"]["code"] == "payment_required"

    payment = client.post(
        f"/api/orders/{order['id']}/payments",
        headers=financial_headers(session, "cancel-payment"),
        json={"amount": 750, "method": "cash"},
    )
    assert payment.status_code == 201
    payment_id = payment.get_json()["data"]["id"]
    cancelled = client.post(
        f"/api/orders/{order['id']}/transition", headers=headers, json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200

    refund = client.post(
        f"/api/orders/{order['id']}/payments/{payment_id}/refunds",
        headers=financial_headers(session, "cancel-refund"),
        json={"amount": 750, "note": "Customer changed the delivery date."},
    )
    assert refund.status_code == 201
    assert refund.get_json()["order"]["payment_status"] == "refunded"
    repeated_refund = client.post(
        f"/api/orders/{order['id']}/payments/{payment_id}/refunds",
        headers=financial_headers(session, "cancel-refund-2"),
        json={"amount": 1},
    )
    assert repeated_refund.status_code == 409


def test_last_active_admin_cannot_be_demoted(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    user_id = session["user"]["id"]
    response = client.patch(f"/api/auth/users/{user_id}", headers=headers, json={"role": "staff"})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "last_admin_protected"


def test_payment_idempotency_replays_a_successful_capture(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    product = client.post(
        "/api/products", headers=headers, json={"sku": "IDEMPOTENT-6", "name": "Idempotent Cake", "unit_price": 300, "stock_quantity": 1}
    ).get_json()["data"]
    order = client.post(
        "/api/orders", headers=headers, json={"items": [{"product_id": product["id"], "quantity": 1}]}
    ).get_json()["data"]
    key = "retry-safe-payment-1"
    first = client.post(
        f"/api/orders/{order['id']}/payments", headers=financial_headers(session, key), json={"amount": 300, "method": "cash"}
    )
    second = client.post(
        f"/api/orders/{order['id']}/payments", headers=financial_headers(session, key), json={"amount": 300, "method": "cash"}
    )
    assert first.status_code == second.status_code == 201
    assert first.get_json()["data"]["id"] == second.get_json()["data"]["id"]
    reused_key = client.post(
        f"/api/orders/{order['id']}/payments", headers=financial_headers(session, key), json={"amount": 200, "method": "cash"}
    )
    assert reused_key.status_code == 409
    assert reused_key.get_json()["error"]["code"] == "idempotency_key_reused"


def test_dashboard_returns_a_gap_free_local_seven_day_net_payment_series(app, client, monkeypatch):
    fixed_now = datetime(2030, 2, 3, 18, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(resources, "utc_now", lambda: fixed_now)
    session = bootstrap(client)
    headers = auth_headers(session)
    product = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "DASHBOARD-6", "name": "Dashboard Cake", "unit_price": 500, "stock_quantity": 4},
    ).get_json()["data"]
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    ).get_json()["data"]

    shop_timezone = ZoneInfo(app.config["SHOP_TIMEZONE"])
    today = fixed_now.astimezone(shop_timezone).date()

    def recorded_at(day, hour):
        return (
            datetime.combine(day, datetime.min.time(), tzinfo=shop_timezone) + timedelta(hours=hour)
        ).astimezone(timezone.utc)

    with app.app_context():
        db.session.add_all(
            [
                Payment(
                    order_id=order["id"],
                    created_by_user_id=session["user"]["id"],
                    amount=Decimal("200.00"),
                    method="cash",
                    status="captured",
                    created_at=recorded_at(today - timedelta(days=6), 12),
                ),
                Payment(
                    order_id=order["id"],
                    created_by_user_id=session["user"]["id"],
                    amount=Decimal("20.00"),
                    method="cash",
                    status="refunded",
                    created_at=recorded_at(today - timedelta(days=2), 12),
                ),
                Payment(
                    order_id=order["id"],
                    created_by_user_id=session["user"]["id"],
                    amount=Decimal("310.00"),
                    method="upi",
                    status="captured",
                    created_at=recorded_at(today, 0),
                ),
                Payment(
                    order_id=order["id"],
                    created_by_user_id=session["user"]["id"],
                    amount=Decimal("85.00"),
                    method="upi",
                    status="refunded",
                    created_at=recorded_at(today, 23),
                ),
                # This event is just outside the seven local business days and
                # must not be leaked into the first chart bar.
                Payment(
                    order_id=order["id"],
                    created_by_user_id=session["user"]["id"],
                    amount=Decimal("999.00"),
                    method="cash",
                    status="captured",
                    created_at=recorded_at(today - timedelta(days=7), 12),
                ),
            ]
        )
        db.session.commit()

    response = client.get("/api/dashboard", headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    series = payload["daily_sales"]
    assert len(series) == 7
    assert [entry["date"] for entry in series] == [
        (today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)
    ]
    by_date = {entry["date"]: entry["net_revenue"] for entry in series}
    assert by_date[(today - timedelta(days=6)).isoformat()] == 200.0
    assert by_date[(today - timedelta(days=2)).isoformat()] == -20.0
    assert by_date[today.isoformat()] == 225.0
    assert by_date[(today - timedelta(days=5)).isoformat()] == 0.0
    assert payload["metrics"]["today_revenue"] == 225.0
