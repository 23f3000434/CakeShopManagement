"""Regression coverage for release-critical API boundaries and role contracts."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import IdempotencyRecord, utc_now


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
        json={
            "full_name": "Asha Owner",
            "email": "owner@butterlane.test",
            "password": "securepassword1",
        },
    )
    assert response.status_code == 201
    return response.get_json()


def auth_headers(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


def financial_headers(session, key):
    return {**auth_headers(session), "Idempotency-Key": key}


def create_product(client, session, *, sku="AUDIT-CAKE", price="20.00", stock=20, cost="7.50"):
    response = client.post(
        "/api/products",
        headers=auth_headers(session),
        json={
            "sku": sku,
            "name": "Audit Cake",
            "unit_price": price,
            "cost_price": cost,
            "stock_quantity": stock,
        },
    )
    assert response.status_code == 201
    return response.get_json()["data"]


def test_archived_customer_and_invalid_email_are_rejected_for_new_orders(client):
    session = bootstrap(client)
    headers = auth_headers(session)
    product = create_product(client, session)

    invalid_email = client.post(
        "/api/customers",
        headers=headers,
        json={"full_name": "Mira Kapoor", "email": "not-an-email"},
    )
    assert invalid_email.status_code == 400
    assert invalid_email.get_json()["error"]["details"]["email"] == "invalid email"

    customer = client.post(
        "/api/customers",
        headers=headers,
        json={"full_name": "Mira Kapoor", "email": "mira@example.test"},
    ).get_json()["data"]
    archived = client.delete(f"/api/customers/{customer['id']}", headers=headers)
    assert archived.status_code == 200

    rejected = client.post(
        "/api/orders",
        headers=headers,
        json={"customer_id": customer["id"], "items": [{"product_id": product["id"], "quantity": 1}]},
    )
    assert rejected.status_code == 409
    assert rejected.get_json()["error"]["code"] == "customer_archived"


def test_database_sized_values_are_validated_before_they_can_raise_server_errors(client):
    session = bootstrap(client)
    headers = auth_headers(session)

    oversized_stock = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "OVERSIZED-STOCK", "name": "Cake", "unit_price": 10, "stock_quantity": 2_147_483_648},
    )
    assert oversized_stock.status_code == 400
    assert oversized_stock.get_json()["error"]["details"]["stock_quantity"] == "maximum 2147483647"

    oversized_price = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "OVERSIZED-PRICE", "name": "Cake", "unit_price": "10000000000.00"},
    )
    assert oversized_price.status_code == 400
    assert oversized_price.get_json()["error"]["details"]["unit_price"] == "maximum 9999999999.99"

    product = create_product(client, session, sku="LINE-LIMIT", price="5.00")
    oversized_line = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 2_147_483_647}]},
    )
    assert oversized_line.status_code == 400
    assert oversized_line.get_json()["error"]["details"]["items"] == "line total too large"

    oversized_adjustment = client.post(
        f"/api/products/{product['id']}/stock-adjustments",
        headers=headers,
        json={"quantity_change": 2_147_483_648, "reason": "restock"},
    )
    assert oversized_adjustment.status_code == 400
    assert oversized_adjustment.get_json()["error"]["details"]["quantity_change"] == "maximum 2147483647"


def test_expired_financial_idempotency_record_allows_a_new_request(client, app):
    session = bootstrap(client)
    product = create_product(client, session)
    order = client.post(
        "/api/orders",
        headers=auth_headers(session),
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    ).get_json()["data"]
    key = "expired-payment-key"

    first = client.post(
        f"/api/orders/{order['id']}/payments",
        headers=financial_headers(session, key),
        json={"amount": "10.00", "method": "cash"},
    )
    assert first.status_code == 201

    with app.app_context():
        record = IdempotencyRecord.query.filter_by(key=key).one()
        record.expires_at = utc_now() - timedelta(seconds=1)
        db.session.commit()

    second = client.post(
        f"/api/orders/{order['id']}/payments",
        headers=financial_headers(session, key),
        json={"amount": "10.00", "method": "cash"},
    )
    assert second.status_code == 201
    assert second.get_json()["data"]["id"] != first.get_json()["data"]["id"]
    assert second.get_json()["order"]["payment_status"] == "paid"


def test_failed_financial_attempt_does_not_reserve_an_idempotency_key(client):
    session = bootstrap(client)
    product = create_product(client, session, price="10.00")
    order = client.post(
        "/api/orders",
        headers=auth_headers(session),
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    ).get_json()["data"]
    key = "recover-after-validation-error"

    rejected = client.post(
        f"/api/orders/{order['id']}/payments",
        headers=financial_headers(session, key),
        json={"amount": "11.00", "method": "cash"},
    )
    assert rejected.status_code == 409
    assert rejected.get_json()["error"]["code"] == "overpayment"

    accepted = client.post(
        f"/api/orders/{order['id']}/payments",
        headers=financial_headers(session, key),
        json={"amount": "10.00", "method": "cash"},
    )
    assert accepted.status_code == 201


def test_staff_permissions_hide_costs_but_preserve_operational_read_access(client):
    admin = bootstrap(client)
    product = create_product(client, admin, stock=1, cost="7.50")
    admin_headers = auth_headers(admin)
    for full_name, email, role in (
        ("Mina Manager", "manager@butterlane.test", "manager"),
        ("Sam Staff", "staff@butterlane.test", "staff"),
    ):
        created = client.post(
            "/api/auth/users",
            headers=admin_headers,
            json={"full_name": full_name, "email": email, "role": role, "password": "anothersecurepassword1"},
        )
        assert created.status_code == 201

    manager = client.post(
        "/api/auth/login",
        json={"email": "manager@butterlane.test", "password": "anothersecurepassword1"},
    ).get_json()
    staff = client.post(
        "/api/auth/login",
        json={"email": "staff@butterlane.test", "password": "anothersecurepassword1"},
    ).get_json()
    staff_headers = auth_headers(staff)

    manager_product = client.get(f"/api/products/{product['id']}", headers=auth_headers(manager))
    assert manager_product.status_code == 200
    assert manager_product.get_json()["data"]["cost_price"] == 7.5

    staff_product = client.get(f"/api/products/{product['id']}", headers=staff_headers)
    assert staff_product.status_code == 200
    assert "cost_price" not in staff_product.get_json()["data"]
    staff_dashboard = client.get("/api/dashboard", headers=staff_headers)
    assert staff_dashboard.status_code == 200
    assert "cost_price" not in staff_dashboard.get_json()["low_stock"][0]
    staff_low_stock = client.get("/api/inventory/low-stock", headers=staff_headers)
    assert staff_low_stock.status_code == 200
    assert "cost_price" not in staff_low_stock.get_json()["data"][0]

    assert client.post("/api/products", headers=staff_headers, json={}).status_code == 403
    assert client.get("/api/reports/sales", headers=staff_headers).status_code == 403
    assert client.get("/api/audit-logs", headers=staff_headers).status_code == 403
    assert client.get("/api/auth/users", headers=staff_headers).status_code == 403
    assert client.get("/api/reports/sales", headers=auth_headers(manager)).status_code == 200
    assert client.get("/api/audit-logs", headers=auth_headers(manager)).status_code == 403


def test_sales_report_rejects_reversed_business_dates_and_timestamps_are_utc(client):
    session = bootstrap(client)
    headers = auth_headers(session)

    report = client.get("/api/reports/sales?from=2030-12-31&to=2030-01-01", headers=headers)
    assert report.status_code == 400
    assert report.get_json()["error"]["details"]["from/to"] == "invalid date range"

    product = create_product(client, session, sku="UTC-TIMESTAMP")
    assert product["created_at"].endswith("+00:00")
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    )
    assert order.status_code == 201
    order_data = order.get_json()["data"]
    assert order_data["created_at"].endswith("+00:00")
    assert len(order_data["order_number"].rsplit("-", 1)[1]) == 12
