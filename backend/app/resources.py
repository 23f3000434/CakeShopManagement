"""Business API: catalogue, customers, orders, stock, and operational reporting."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import case, func, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from .extensions import db
from .models import (
    AuditLog,
    Customer,
    IdempotencyRecord,
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatusEvent,
    Payment,
    Product,
    User,
    money,
    utc_now,
)
from .utils import (
    APIError,
    MAX_DATABASE_INTEGER,
    MAX_DATABASE_MONEY,
    as_bool,
    as_datetime,
    as_decimal,
    as_int,
    current_user,
    optional_http_url,
    optional_string,
    page_args,
    paginated,
    payload,
    required_string,
    role_required,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")
WRITE_ROLES = ("admin", "manager")
ORDER_STATUSES = {"draft", "confirmed", "in_progress", "ready", "completed", "cancelled"}
PAYMENT_STATUSES = {"unpaid", "partial", "paid", "refunded"}
PAYMENT_METHODS = {"cash", "card", "upi", "bank_transfer", "other"}
FULFILLMENT_TYPES = {"pickup", "delivery"}
ALLOWED_TRANSITIONS = {
    "draft": {"confirmed", "cancelled"},
    "confirmed": {"in_progress", "cancelled"},
    "in_progress": {"ready", "cancelled"},
    "ready": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}
IDEMPOTENCY_TTL = timedelta(hours=24)
CUSTOMER_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _audit(actor: User | None, action: str, entity_type: str, entity_id: int | str, details: dict | None = None) -> None:
    db.session.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details,
        )
    )


def _product_data(product: Product, actor: User) -> dict:
    """Keep unit costs visible only to the roles entrusted with margins."""
    return product.to_dict(include_cost_price=actor.role in WRITE_ROLES)


def _commit() -> None:
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        message = "This record conflicts with existing business data."
        if "sku" in str(error.orig).lower():
            message = "That SKU is already in use."
        raise APIError(message, 409, "conflict")
    except StaleDataError:
        db.session.rollback()
        raise APIError(
            "This record changed while you were working. Refresh and try again.",
            409,
            "stale_record",
        )


def _start_idempotent_mutation(actor: User, endpoint: str, data: dict):
    """Reserve a financial request key or replay its prior successful result."""
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise APIError(
            "An Idempotency-Key header (up to 128 characters) is required for financial actions.",
            400,
            "idempotency_key_required",
        )
    request_hash = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()

    def existing_response(existing: IdempotencyRecord):
        if existing.request_hash != request_hash:
            raise APIError(
                "This Idempotency-Key was already used with a different request.",
                409,
                "idempotency_key_reused",
            )
        if existing.status_code is None or existing.response_body is None:
            raise APIError("This financial action is already being processed.", 409, "idempotency_in_progress")
        return None, (jsonify(existing.response_body), existing.status_code)

    now = utc_now()
    existing = db.session.execute(
        db.select(IdempotencyRecord)
        .where(
            IdempotencyRecord.user_id == actor.id,
            IdempotencyRecord.endpoint == endpoint,
            IdempotencyRecord.key == key,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if existing:
        expires_at = existing.expires_at
        # SQLite does not preserve timezone information for DateTime columns.
        # Idempotency timestamps are written in UTC, so restore it for the
        # expiry comparison in local development and tests.
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now:
            return existing_response(existing)
        db.session.delete(existing)
        db.session.flush()

    record = IdempotencyRecord(
        user_id=actor.id,
        endpoint=endpoint,
        key=key,
        request_hash=request_hash,
        expires_at=now + IDEMPOTENCY_TTL,
    )
    db.session.add(record)
    try:
        db.session.flush()
    except IntegrityError:
        # Concurrent retry: the unique index waits for the original request to
        # finish, then lets us replay its exact persisted response.
        db.session.rollback()
        existing = IdempotencyRecord.query.filter_by(user_id=actor.id, endpoint=endpoint, key=key).first()
        if existing:
            return existing_response(existing)
        raise APIError("Could not reserve the request key. Please retry.", 409, "idempotency_conflict")
    return record, None


def _finish_idempotent_mutation(record: IdempotencyRecord, response_body: dict, status_code: int) -> None:
    record.response_body = response_body
    record.status_code = status_code


def _flush() -> None:
    """Flush IDs early while translating database conflicts into API errors."""
    try:
        db.session.flush()
    except IntegrityError as error:
        db.session.rollback()
        message = "This record conflicts with existing business data."
        if "sku" in str(error.orig).lower():
            message = "That SKU is already in use."
        raise APIError(message, 409, "conflict")
    except StaleDataError:
        db.session.rollback()
        raise APIError("This record changed while you were working. Refresh and try again.", 409, "stale_record")


def _require_version(data: dict, entity) -> None:
    """Optionally protect UI edits from silently overwriting a newer change."""
    if "version" not in data:
        return
    incoming = as_int(data["version"], "version", minimum=1, maximum=MAX_DATABASE_INTEGER)
    if incoming != entity.version:
        raise APIError(
            "This record changed since you opened it. Refresh and review the latest version.",
            409,
            "stale_record",
            {"current_version": entity.version},
        )


def _order_number() -> str:
    # A 48-bit suffix keeps a collision astronomically unlikely even on a busy
    # day, while staying comfortably inside the persisted 32-character field.
    return f"CK-{utc_now().astimezone(_shop_timezone()):%Y%m%d}-{uuid4().hex[:12].upper()}"


def _shop_timezone() -> ZoneInfo:
    return ZoneInfo(current_app.config["SHOP_TIMEZONE"])


def _business_day_start() -> datetime:
    local_now = utc_now().astimezone(_shop_timezone())
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _business_day_start_for(business_date) -> datetime:
    """Return the UTC instant at the start of a calendar day in the shop timezone."""
    return datetime.combine(
        business_date, datetime.min.time(), tzinfo=_shop_timezone()
    ).astimezone(timezone.utc)


def _daily_net_payment_series(days: int = 7) -> list[dict]:
    """Build a gap-free, shop-timezone sales series from the payment ledger.

    A payment is recognised on the local business date when it was recorded.
    Captures add to the day and refunds subtract from it, so the dashboard never
    treats an order total as cash that was actually retained.
    """
    shop_timezone = _shop_timezone()
    today = utc_now().astimezone(shop_timezone).date()
    business_dates = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    range_start = _business_day_start_for(business_dates[0])
    range_end = _business_day_start_for(today + timedelta(days=1))
    totals = {business_date: Decimal("0.00") for business_date in business_dates}

    payments = Payment.query.filter(
        Payment.status.in_(("captured", "refunded")),
        Payment.created_at >= range_start,
        Payment.created_at < range_end,
    ).all()
    for payment in payments:
        recorded_at = payment.created_at
        # SQLite does not round-trip timezone information even for a timezone
        # aware column. Application writes are UTC, so restore that fact before
        # assigning the ledger event to its local business day.
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        business_date = recorded_at.astimezone(shop_timezone).date()
        if business_date in totals:
            totals[business_date] += payment.amount if payment.status == "captured" else -payment.amount

    return [
        {
            "date": business_date.isoformat(),
            "label": business_date.strftime("%a"),
            "net_revenue": money(totals[business_date]),
        }
        for business_date in business_dates
    ]


def _report_date_boundary(value: str, *, exclusive_end: bool = False) -> datetime:
    """Interpret YYYY-MM-DD as a calendar day in the configured shop timezone."""
    try:
        business_date = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise APIError("Dates must use YYYY-MM-DD.", details={"from/to": "invalid date"})
    if exclusive_end:
        business_date += timedelta(days=1)
    return _business_day_start_for(business_date)


def _customer_or_404(customer_id: int) -> Customer:
    customer = db.session.get(Customer, customer_id)
    if not customer:
        raise APIError("Customer not found.", 404, "not_found")
    return customer


def _active_customer_or_404(customer_id: int) -> Customer:
    customer = _customer_or_404(customer_id)
    if not customer.is_active:
        raise APIError("Archived customers cannot be assigned to a new order.", 409, "customer_archived")
    return customer


def _customer_email(data: dict) -> str | None:
    email = optional_string(data, "email", max_length=255)
    if email is None:
        return None
    email = email.lower()
    if not CUSTOMER_EMAIL_PATTERN.match(email):
        raise APIError("Enter a valid email address.", details={"email": "invalid email"})
    return email


def _product_or_404(product_id: int) -> Product:
    product = db.session.get(Product, product_id)
    if not product:
        raise APIError("Product not found.", 404, "not_found")
    return product


def _order_or_404(order_id: int) -> Order:
    order = db.session.get(Order, order_id)
    if not order:
        raise APIError("Order not found.", 404, "not_found")
    return order


def _locked_product_or_404(product_id: int) -> Product:
    product = db.session.execute(
        db.select(Product).where(Product.id == product_id).with_for_update()
    ).scalar_one_or_none()
    if not product:
        raise APIError("Product not found.", 404, "not_found")
    return product


def _locked_order_or_404(order_id: int) -> Order:
    order = db.session.execute(
        db.select(Order).where(Order.id == order_id).with_for_update()
    ).scalar_one_or_none()
    if not order:
        raise APIError("Order not found.", 404, "not_found")
    return order


def _locked_customer(customer_id: int) -> Customer | None:
    return db.session.execute(
        db.select(Customer).where(Customer.id == customer_id).with_for_update()
    ).scalar_one_or_none()


def _apply_product_data(product: Product, data: dict, *, creating: bool = False) -> None:
    required = ("sku", "name", "unit_price") if creating else ()
    for field in required:
        if field not in data:
            required_string(data, field)

    if "sku" in data:
        product.sku = required_string(data, "sku", max_length=64).upper()
    if "name" in data:
        product.name = required_string(data, "name", max_length=160)
    if "category" in data:
        product.category = required_string(data, "category", max_length=80)
    elif creating:
        product.category = "Cakes"
    if "description" in data:
        product.description = optional_string(data, "description", max_length=5000)
    if "unit_price" in data:
        product.unit_price = as_decimal(
            data["unit_price"],
            "unit_price",
            minimum=Decimal("0.00"),
            maximum=MAX_DATABASE_MONEY,
        )
    if "cost_price" in data:
        product.cost_price = (
            as_decimal(
                data["cost_price"],
                "cost_price",
                minimum=Decimal("0.00"),
                maximum=MAX_DATABASE_MONEY,
            )
            if data["cost_price"] not in (None, "")
            else None
        )
    if "stock_quantity" in data:
        if not creating:
            raise APIError(
                "Use the stock-adjustments endpoint to change stock so the audit ledger remains accurate.",
                409,
                "stock_adjustment_required",
            )
        product.stock_quantity = as_int(
            data["stock_quantity"],
            "stock_quantity",
            minimum=0,
            maximum=MAX_DATABASE_INTEGER,
        )
    if "reorder_level" in data:
        product.reorder_level = as_int(
            data["reorder_level"],
            "reorder_level",
            minimum=0,
            maximum=MAX_DATABASE_INTEGER,
        )
    elif creating:
        product.reorder_level = 5
    if "image_url" in data:
        product.image_url = optional_http_url(data, "image_url")
    if "is_active" in data:
        product.is_active = as_bool(data["is_active"], "is_active")


def _order_item_specs(raw_items: object) -> list[dict]:
    if not isinstance(raw_items, list) or not raw_items:
        raise APIError("An order must contain at least one item.", details={"items": "required"})
    if len(raw_items) > 100:
        raise APIError("An order cannot contain more than 100 line items.", details={"items": "too many items"})

    specs_by_product: dict[int, dict] = {}
    for position, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise APIError("Each order item must be an object.", details={"items": f"item {position} is invalid"})
        product_id = as_int(
            raw.get("product_id"),
            f"items[{position}].product_id",
            minimum=1,
            maximum=MAX_DATABASE_INTEGER,
        )
        quantity = as_int(
            raw.get("quantity"),
            f"items[{position}].quantity",
            minimum=1,
            maximum=MAX_DATABASE_INTEGER,
        )
        if product_id in specs_by_product:
            combined_quantity = specs_by_product[product_id]["quantity"] + quantity
            if combined_quantity > MAX_DATABASE_INTEGER:
                raise APIError(
                    "Combined quantity is above the allowed maximum.",
                    details={"items": "quantity too large"},
                )
            specs_by_product[product_id]["quantity"] = combined_quantity
            continue
        product = _product_or_404(product_id)
        if not product.is_active:
            raise APIError(f"{product.name} is archived and cannot be added to a new order.", 409, "product_archived")
        specs_by_product[product_id] = {"product": product, "quantity": quantity}
    return list(specs_by_product.values())


def _replace_order_items(order: Order, raw_items: object) -> None:
    if order.stock_applied_at:
        raise APIError("Items cannot be changed after stock has been committed.", 409, "order_locked")
    specs = _order_item_specs(raw_items)
    order.items.clear()
    subtotal = Decimal("0.00")
    for spec in specs:
        product = spec["product"]
        line_total = product.unit_price * spec["quantity"]
        if line_total > MAX_DATABASE_MONEY:
            raise APIError("An order line total is above the allowed maximum.", details={"items": "line total too large"})
        subtotal += line_total
        if subtotal > MAX_DATABASE_MONEY:
            raise APIError("Order subtotal is above the allowed maximum.", details={"items": "subtotal too large"})
        order.items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                unit_price=product.unit_price,
                quantity=spec["quantity"],
                line_total=line_total,
            )
        )
    order.subtotal = subtotal
    _calculate_order_totals(order)


def _calculate_order_totals(order: Order) -> None:
    discount = order.discount_amount or Decimal("0.00")
    if discount > order.subtotal:
        raise APIError("Discount cannot exceed the item subtotal.", details={"discount_amount": "exceeds subtotal"})
    taxable_amount = order.subtotal - discount
    order.tax_amount = (taxable_amount * (order.tax_rate or Decimal("0.00")) / Decimal("100")).quantize(Decimal("0.01"))
    order.total_amount = taxable_amount + order.tax_amount
    if order.tax_amount > MAX_DATABASE_MONEY or order.total_amount > MAX_DATABASE_MONEY:
        raise APIError("Order total is above the allowed maximum.", details={"total_amount": "maximum exceeded"})


def _apply_order_data(order: Order, data: dict, *, creating: bool = False) -> None:
    if "customer_id" in data:
        customer_id = data["customer_id"]
        order.customer_id = (
            None
            if customer_id in (None, "")
            else _active_customer_or_404(
                as_int(customer_id, "customer_id", minimum=1, maximum=MAX_DATABASE_INTEGER)
            ).id
        )
    if "fulfillment_type" in data:
        fulfillment_type = required_string(data, "fulfillment_type", max_length=24).lower()
        if fulfillment_type not in FULFILLMENT_TYPES:
            raise APIError("Fulfillment type must be pickup or delivery.", details={"fulfillment_type": "invalid value"})
        order.fulfillment_type = fulfillment_type
    elif creating:
        order.fulfillment_type = "pickup"
    if "pickup_at" in data:
        order.pickup_at = as_datetime(data["pickup_at"], "pickup_at")
    if "delivery_address" in data:
        order.delivery_address = optional_string(data, "delivery_address", max_length=5000)
    if order.fulfillment_type == "delivery" and not order.delivery_address:
        raise APIError("A delivery address is required for delivery orders.", details={"delivery_address": "required"})
    if "notes" in data:
        order.notes = optional_string(data, "notes", max_length=5000)
    if "discount_amount" in data:
        order.discount_amount = as_decimal(
            data["discount_amount"],
            "discount_amount",
            minimum=Decimal("0.00"),
            maximum=MAX_DATABASE_MONEY,
        )
    elif creating:
        order.discount_amount = Decimal("0.00")
    if "tax_rate" in data:
        order.tax_rate = as_decimal(
            data["tax_rate"],
            "tax_rate",
            minimum=Decimal("0.00"),
            maximum=Decimal("100.00"),
        )
        if order.tax_rate > Decimal("100.00"):
            raise APIError("Tax rate cannot exceed 100%.", details={"tax_rate": "maximum 100"})
    elif creating:
        order.tax_rate = Decimal("0.00")


def _add_inventory_movement(
    product: Product,
    quantity_change: int,
    reason: str,
    user: User,
    *,
    order: Order | None = None,
    note: str | None = None,
) -> None:
    product.stock_quantity += quantity_change
    db.session.add(
        InventoryMovement(
            product_id=product.id,
            order_id=order.id if order else None,
            created_by_user_id=user.id,
            quantity_change=quantity_change,
            reason=reason,
            note=note,
        )
    )


def _apply_order_stock(order: Order, user: User) -> None:
    """Commit stock once at confirmation using row locks on PostgreSQL."""
    if order.stock_applied_at:
        return
    product_ids = sorted({item.product_id for item in order.items if item.product_id})
    locked_products = {
        product.id: product
        for product in db.session.execute(
            db.select(Product).where(Product.id.in_(product_ids)).order_by(Product.id).with_for_update()
        ).scalars()
    }
    for item in order.items:
        product = locked_products.get(item.product_id)
        if not product:
            raise APIError(f"Product for {item.product_name} no longer exists.", 409, "missing_product")
        if product.stock_quantity < item.quantity:
            raise APIError(
                f"Not enough stock for {product.name}. Available: {product.stock_quantity}.",
                409,
                "insufficient_stock",
                {"product_id": product.id, "available": product.stock_quantity, "requested": item.quantity},
            )
    for item in order.items:
        product = locked_products[item.product_id]
        _add_inventory_movement(product, -item.quantity, "order_confirmed", user, order=order)
    order.stock_applied_at = utc_now()


def _restore_order_stock(order: Order, user: User) -> None:
    if not order.stock_applied_at:
        return
    product_ids = sorted({item.product_id for item in order.items if item.product_id})
    locked_products = {
        product.id: product
        for product in db.session.execute(
            db.select(Product).where(Product.id.in_(product_ids)).order_by(Product.id).with_for_update()
        ).scalars()
    }
    for item in order.items:
        product = locked_products.get(item.product_id)
        if product:
            _add_inventory_movement(product, item.quantity, "order_cancelled", user, order=order)
    order.stock_applied_at = None


def _refresh_customer_metrics(customer: Customer | None) -> None:
    if not customer:
        return
    # Completing or refunding any order for a customer takes this row lock so
    # concurrent transactions cannot overwrite the persisted lifetime totals.
    customer = _locked_customer(customer.id)
    if not customer:
        return
    completed = Order.query.filter_by(customer_id=customer.id, status="completed")
    customer.completed_order_count = completed.count()
    customer.total_spent = _net_payment_total(completed)


def _recalculate_payment_status(order: Order) -> None:
    captured, refunded = _payment_totals(order)
    net_paid = captured - refunded
    if refunded and net_paid <= 0:
        order.payment_status = "refunded"
    elif net_paid <= 0:
        order.payment_status = "unpaid"
    elif net_paid < order.total_amount:
        order.payment_status = "partial"
    else:
        order.payment_status = "paid"


def _payment_totals(order: Order) -> tuple[Decimal, Decimal]:
    """Read the committed payment ledger, avoiding stale relationship caches."""
    payments = Payment.query.filter_by(order_id=order.id).all()
    captured = sum((payment.amount for payment in payments if payment.status == "captured"), Decimal("0.00"))
    refunded = sum((payment.amount for payment in payments if payment.status == "refunded"), Decimal("0.00"))
    return captured, refunded


def _payment_net_expression():
    return case(
        (Payment.status == "captured", Payment.amount),
        (Payment.status == "refunded", -Payment.amount),
        else_=0,
    )


def _net_payment_total(order_query) -> Decimal:
    """Return cash collected less refunds for the orders represented by a query."""
    order_ids = order_query.with_entities(Order.id).subquery()
    return (
        db.session.query(func.coalesce(func.sum(_payment_net_expression()), 0))
        .filter(Payment.order_id.in_(db.select(order_ids.c.id)))
        .scalar()
        or Decimal("0.00")
    )


@api_bp.get("/health")
def health():
    """Expose readiness only when the application can reach its database."""
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"status": "unavailable", "service": "cake-shop-api"}), 503
    return jsonify({"status": "ok", "service": "cake-shop-api", "time": utc_now().isoformat()})


@api_bp.get("/dashboard")
@role_required("admin", "manager", "staff")
def dashboard():
    actor = current_user()
    day_start = _business_day_start()
    daily_sales = _daily_net_payment_series()
    today_revenue = Decimal(str(daily_sales[-1]["net_revenue"]))
    today_gross_sales = (
        Order.query.filter(Order.status == "completed", Order.completed_at >= day_start)
        .with_entities(func.coalesce(func.sum(Order.total_amount), 0))
        .scalar()
        or Decimal("0.00")
    )
    pending_statuses = ("confirmed", "in_progress", "ready")
    pending_orders = Order.query.filter(Order.status.in_(pending_statuses)).count()
    low_stock_query = Product.query.filter(
        Product.is_active.is_(True), Product.stock_quantity <= Product.reorder_level
    )
    low_stock = low_stock_query.order_by(Product.stock_quantity.asc()).limit(8).all()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    production_queue = Order.query.filter(Order.status.in_(pending_statuses)).order_by(Order.pickup_at.asc().nullslast(), Order.created_at.asc()).limit(8).all()
    return jsonify(
        {
            "metrics": {
                "today_revenue": money(today_revenue),
                "today_gross_sales": money(today_gross_sales),
                "pending_orders": pending_orders,
                "low_stock_count": low_stock_query.count(),
                "active_products": Product.query.filter_by(is_active=True).count(),
            },
            "daily_sales": daily_sales,
            "low_stock": [_product_data(product, actor) for product in low_stock],
            "recent_orders": [order.to_dict(include_items=False) for order in recent_orders],
            "production_queue": [order.to_dict(include_items=False) for order in production_queue],
        }
    )


@api_bp.get("/products")
@role_required("admin", "manager", "staff")
def list_products():
    actor = current_user()
    page, per_page = page_args(request)
    query = Product.query
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    active = request.args.get("active")
    low_stock = request.args.get("low_stock")
    if search:
        term = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(term), Product.sku.ilike(term), Product.category.ilike(term)))
    if category:
        query = query.filter(Product.category == category)
    if active in {"true", "false"}:
        query = query.filter(Product.is_active.is_(active == "true"))
    if low_stock == "true":
        query = query.filter(Product.stock_quantity <= Product.reorder_level)
    return jsonify(
        paginated(
            query.order_by(Product.is_active.desc(), Product.name.asc()),
            page,
            per_page,
            lambda product: _product_data(product, actor),
        )
    )


@api_bp.post("/products")
@role_required(*WRITE_ROLES)
def create_product():
    data = payload(request)
    product = Product()
    _apply_product_data(product, data, creating=True)
    db.session.add(product)
    _flush()
    initial_stock = product.stock_quantity
    if initial_stock:
        db.session.add(
            InventoryMovement(
                product_id=product.id,
                created_by_user_id=current_user().id,
                quantity_change=initial_stock,
                reason="initial_stock",
                note="Opening stock recorded when product was created.",
            )
        )
    _audit(current_user(), "product.created", "product", product.id, {"sku": product.sku})
    _commit()
    return jsonify({"data": _product_data(product, current_user())}), 201


@api_bp.get("/products/<int:product_id>")
@role_required("admin", "manager", "staff")
def get_product(product_id: int):
    return jsonify({"data": _product_data(_product_or_404(product_id), current_user())})


@api_bp.patch("/products/<int:product_id>")
@role_required(*WRITE_ROLES)
def update_product(product_id: int):
    product = _product_or_404(product_id)
    data = payload(request)
    _require_version(data, product)
    old_price = product.unit_price
    _apply_product_data(product, data)
    actor = current_user()
    details = {"sku": product.sku}
    if old_price != product.unit_price:
        details.update({"old_price": money(old_price), "new_price": money(product.unit_price)})
    _audit(actor, "product.updated", "product", product.id, details)
    _commit()
    return jsonify({"data": _product_data(product, actor)})


@api_bp.delete("/products/<int:product_id>")
@role_required(*WRITE_ROLES)
def archive_product(product_id: int):
    product = _product_or_404(product_id)
    product.is_active = False
    _audit(current_user(), "product.archived", "product", product.id, {"sku": product.sku})
    _commit()
    return jsonify({"message": "Product archived. Historical orders remain intact.", "data": _product_data(product, current_user())})


@api_bp.post("/products/<int:product_id>/stock-adjustments")
@role_required(*WRITE_ROLES)
def adjust_stock(product_id: int):
    product = _locked_product_or_404(product_id)
    data = payload(request)
    quantity_change = as_int(
        data.get("quantity_change"),
        "quantity_change",
        minimum=-MAX_DATABASE_INTEGER,
        maximum=MAX_DATABASE_INTEGER,
    )
    if quantity_change == 0:
        raise APIError("Stock adjustment cannot be zero.", details={"quantity_change": "non-zero required"})
    reason = required_string(data, "reason", max_length=32).lower()
    if reason not in {"restock", "adjustment", "waste", "return"}:
        raise APIError("Reason must be restock, adjustment, waste, or return.", details={"reason": "invalid reason"})
    if product.stock_quantity + quantity_change < 0:
        raise APIError("This adjustment would make stock negative.", 409, "negative_stock")
    note = optional_string(data, "note", max_length=500)
    actor = current_user()
    _add_inventory_movement(product, quantity_change, reason, actor, note=note)
    _audit(actor, "inventory.adjusted", "product", product.id, {"quantity_change": quantity_change, "reason": reason, "note": note})
    _commit()
    return jsonify({"data": _product_data(product, actor)}), 201


@api_bp.get("/inventory/movements")
@role_required("admin", "manager", "staff")
def list_inventory_movements():
    page, per_page = page_args(request)
    query = InventoryMovement.query
    product_id = request.args.get("product_id")
    if product_id:
        query = query.filter_by(
            product_id=as_int(product_id, "product_id", minimum=1, maximum=MAX_DATABASE_INTEGER)
        )
    return jsonify(paginated(query.order_by(InventoryMovement.created_at.desc()), page, per_page, lambda movement: movement.to_dict()))


@api_bp.get("/inventory/low-stock")
@role_required("admin", "manager", "staff")
def list_low_stock():
    products = Product.query.filter(Product.is_active.is_(True), Product.stock_quantity <= Product.reorder_level).order_by(Product.stock_quantity.asc()).all()
    actor = current_user()
    return jsonify({"data": [_product_data(product, actor) for product in products]})


@api_bp.get("/customers")
@role_required("admin", "manager", "staff")
def list_customers():
    page, per_page = page_args(request)
    query = Customer.query
    search = request.args.get("search", "").strip()
    active = request.args.get("active")
    if search:
        term = f"%{search}%"
        query = query.filter(or_(Customer.full_name.ilike(term), Customer.email.ilike(term), Customer.phone.ilike(term)))
    if active in {"true", "false"}:
        query = query.filter(Customer.is_active.is_(active == "true"))
    return jsonify(paginated(query.order_by(Customer.full_name.asc()), page, per_page, lambda customer: customer.to_dict()))


@api_bp.post("/customers")
@role_required(*WRITE_ROLES)
def create_customer():
    data = payload(request)
    email = _customer_email(data)
    if email:
        email = email.lower()
        if Customer.query.filter_by(email=email).first():
            raise APIError("A customer already exists with this email.", 409, "duplicate_email")
    customer = Customer(
        full_name=required_string(data, "full_name", max_length=160),
        email=email,
        phone=optional_string(data, "phone", max_length=32),
        address=optional_string(data, "address", max_length=5000),
        notes=optional_string(data, "notes", max_length=5000),
    )
    db.session.add(customer)
    _flush()
    _audit(current_user(), "customer.created", "customer", customer.id, {"full_name": customer.full_name})
    _commit()
    return jsonify({"data": customer.to_dict()}), 201


@api_bp.get("/customers/<int:customer_id>")
@role_required("admin", "manager", "staff")
def get_customer(customer_id: int):
    return jsonify({"data": _customer_or_404(customer_id).to_dict(include_orders=True)})


@api_bp.patch("/customers/<int:customer_id>")
@role_required(*WRITE_ROLES)
def update_customer(customer_id: int):
    customer = _customer_or_404(customer_id)
    data = payload(request)
    if "full_name" in data:
        customer.full_name = required_string(data, "full_name", max_length=160)
    if "email" in data:
        email = _customer_email(data)
        if email:
            email = email.lower()
            duplicate = Customer.query.filter(Customer.email == email, Customer.id != customer.id).first()
            if duplicate:
                raise APIError("A customer already exists with this email.", 409, "duplicate_email")
        customer.email = email
    if "phone" in data:
        customer.phone = optional_string(data, "phone", max_length=32)
    if "address" in data:
        customer.address = optional_string(data, "address", max_length=5000)
    if "notes" in data:
        customer.notes = optional_string(data, "notes", max_length=5000)
    if "is_active" in data:
        customer.is_active = as_bool(data["is_active"], "is_active")
    _audit(current_user(), "customer.updated", "customer", customer.id, {"full_name": customer.full_name})
    _commit()
    return jsonify({"data": customer.to_dict()})


@api_bp.delete("/customers/<int:customer_id>")
@role_required(*WRITE_ROLES)
def archive_customer(customer_id: int):
    customer = _customer_or_404(customer_id)
    customer.is_active = False
    _audit(current_user(), "customer.archived", "customer", customer.id, {"full_name": customer.full_name})
    _commit()
    return jsonify({"message": "Customer archived. Order history is retained.", "data": customer.to_dict()})


@api_bp.get("/orders")
@role_required("admin", "manager", "staff")
def list_orders():
    page, per_page = page_args(request)
    query = Order.query
    status = request.args.get("status", "").strip().lower()
    search = request.args.get("search", "").strip()
    customer_id = request.args.get("customer_id")
    if status:
        if status not in ORDER_STATUSES:
            raise APIError("Unknown order status.", details={"status": "invalid value"})
        query = query.filter(Order.status == status)
    if customer_id:
        query = query.filter(
            Order.customer_id == as_int(customer_id, "customer_id", minimum=1, maximum=MAX_DATABASE_INTEGER)
        )
    if search:
        term = f"%{search}%"
        query = query.outerjoin(Customer).filter(or_(Order.order_number.ilike(term), Customer.full_name.ilike(term)))
    return jsonify(paginated(query.order_by(Order.created_at.desc()), page, per_page, lambda order: order.to_dict(include_items=False)))


@api_bp.post("/orders")
@role_required(*WRITE_ROLES)
def create_order():
    data = payload(request)
    actor = current_user()
    order = Order(order_number=_order_number(), created_by_user_id=actor.id, status="draft")
    _apply_order_data(order, data, creating=True)
    _replace_order_items(order, data.get("items"))
    db.session.add(order)
    _flush()
    db.session.add(
        OrderStatusEvent(
            order_id=order.id,
            changed_by_user_id=actor.id,
            from_status=None,
            to_status="draft",
            note="Order created.",
        )
    )
    _audit(actor, "order.created", "order", order.id, {"order_number": order.order_number, "total": money(order.total_amount)})
    _commit()
    return jsonify({"data": order.to_dict()}), 201


@api_bp.get("/orders/<int:order_id>")
@role_required("admin", "manager", "staff")
def get_order(order_id: int):
    return jsonify({"data": _order_or_404(order_id).to_dict()})


@api_bp.patch("/orders/<int:order_id>")
@role_required(*WRITE_ROLES)
def update_order(order_id: int):
    order = _order_or_404(order_id)
    if order.status != "draft":
        raise APIError("Only draft orders can be edited. Use the lifecycle action to change an active order.", 409, "order_locked")
    data = payload(request)
    _require_version(data, order)
    _apply_order_data(order, data)
    if "items" in data:
        _replace_order_items(order, data["items"])
    else:
        _calculate_order_totals(order)
    _audit(current_user(), "order.updated", "order", order.id, {"order_number": order.order_number})
    _commit()
    return jsonify({"data": order.to_dict()})


@api_bp.post("/orders/<int:order_id>/transition")
@role_required(*WRITE_ROLES)
def transition_order(order_id: int):
    order = _locked_order_or_404(order_id)
    data = payload(request)
    _require_version(data, order)
    target = required_string(data, "status", max_length=24).lower()
    if target not in ORDER_STATUSES:
        raise APIError("Unknown order status.", details={"status": "invalid value"})
    if target not in ALLOWED_TRANSITIONS[order.status]:
        raise APIError(f"An order cannot move from {order.status} to {target}.", 409, "invalid_transition")

    actor = current_user()
    old_status = order.status
    if target == "confirmed":
        _apply_order_stock(order, actor)
    elif target == "cancelled":
        _restore_order_stock(order, actor)
    elif target == "completed" and order.payment_status != "paid":
        raise APIError(
            "A completed order must be fully paid. Record the payment first.",
            409,
            "payment_required",
        )
    order.status = target
    if target == "completed":
        order.completed_at = utc_now()
    db.session.add(
        OrderStatusEvent(
            order_id=order.id,
            changed_by_user_id=actor.id,
            from_status=old_status,
            to_status=target,
            note=optional_string(data, "note", max_length=500),
        )
    )
    if target in {"completed", "cancelled"} or old_status == "completed":
        _refresh_customer_metrics(order.customer)
    _audit(actor, "order.status_changed", "order", order.id, {"from": old_status, "to": target})
    _commit()
    return jsonify({"data": order.to_dict()})


@api_bp.post("/orders/<int:order_id>/payments")
@role_required(*WRITE_ROLES)
def add_payment(order_id: int):
    data = payload(request)
    actor = current_user()
    idempotency_record, replay = _start_idempotent_mutation(
        actor, f"/orders/{order_id}/payments", data
    )
    if replay:
        return replay
    order = _locked_order_or_404(order_id)
    if order.status == "cancelled":
        raise APIError("Payments cannot be recorded against a cancelled order.", 409, "order_cancelled")
    amount = as_decimal(
        data.get("amount"),
        "amount",
        minimum=Decimal("0.01"),
        maximum=MAX_DATABASE_MONEY,
    )
    method = required_string(data, "method", max_length=40).lower()
    if method not in PAYMENT_METHODS:
        raise APIError("Payment method is not supported.", details={"method": "invalid value"})
    if data.get("status") not in (None, "", "captured"):
        raise APIError(
            "Use the dedicated refund endpoint for refunds; captures are the only payment type accepted here.",
            details={"status": "invalid for payment capture"},
        )
    provider_reference = optional_string(data, "provider_reference", max_length=160)
    if provider_reference and Payment.query.filter_by(provider_reference=provider_reference).first():
        raise APIError("That payment provider reference has already been recorded.", 409, "duplicate_payment")
    captured_total, refunded_total = _payment_totals(order)
    net_paid = captured_total - refunded_total
    if net_paid + amount > order.total_amount:
        raise APIError(
            "This capture would exceed the order total. Record a payment for the remaining balance only.",
            409,
            "overpayment",
            {"remaining_balance": money(order.total_amount - net_paid)},
        )
    payment = Payment(
        order_id=order.id,
        created_by_user_id=actor.id,
        amount=amount,
        method=method,
        status="captured",
        provider_reference=provider_reference,
        note=optional_string(data, "note", max_length=500),
    )
    db.session.add(payment)
    _flush()
    _recalculate_payment_status(order)
    db.session.expire(order, ["payments"])
    if order.status == "completed":
        _refresh_customer_metrics(order.customer)
    _audit(actor, "payment.recorded", "payment", payment.id, {"order_number": order.order_number, "amount": money(amount), "method": method})
    response_body = {"data": payment.to_dict(), "order": order.to_dict()}
    _finish_idempotent_mutation(idempotency_record, response_body, 201)
    _commit()
    return jsonify(response_body), 201


@api_bp.post("/orders/<int:order_id>/payments/<int:payment_id>/refunds")
@role_required(*WRITE_ROLES)
def refund_payment(order_id: int, payment_id: int):
    """Issue a bounded refund tied to the original captured payment."""
    data = payload(request)
    actor = current_user()
    idempotency_record, replay = _start_idempotent_mutation(
        actor, f"/orders/{order_id}/payments/{payment_id}/refunds", data
    )
    if replay:
        return replay
    order = _locked_order_or_404(order_id)
    source_payment = db.session.execute(
        db.select(Payment)
        .where(Payment.id == payment_id, Payment.order_id == order.id)
        .with_for_update()
    ).scalar_one_or_none()
    if not source_payment:
        raise APIError("Original payment not found on this order.", 404, "not_found")
    if source_payment.status != "captured":
        raise APIError("Only captured payments can be refunded.", 409, "refund_unavailable")

    amount = as_decimal(
        data.get("amount"),
        "amount",
        minimum=Decimal("0.01"),
        maximum=MAX_DATABASE_MONEY,
    )
    prior_refunds = (
        Payment.query.filter_by(refunded_payment_id=source_payment.id, status="refunded")
        .with_entities(func.coalesce(func.sum(Payment.amount), 0))
        .scalar()
        or Decimal("0.00")
    )
    remaining = source_payment.amount - prior_refunds
    if amount > remaining:
        raise APIError(
            "Refund cannot exceed the unrefunded amount of the original payment.",
            409,
            "over_refund",
            {"refundable_balance": money(remaining)},
        )
    provider_reference = optional_string(data, "provider_reference", max_length=160)
    if provider_reference and Payment.query.filter_by(provider_reference=provider_reference).first():
        raise APIError("That payment provider reference has already been recorded.", 409, "duplicate_payment")
    refund = Payment(
        order_id=order.id,
        created_by_user_id=actor.id,
        amount=amount,
        method=source_payment.method,
        status="refunded",
        refunded_payment_id=source_payment.id,
        provider_reference=provider_reference,
        note=optional_string(data, "note", max_length=500),
    )
    db.session.add(refund)
    _flush()
    _recalculate_payment_status(order)
    db.session.expire(order, ["payments"])
    if order.status == "completed":
        _refresh_customer_metrics(order.customer)
    _audit(
        actor,
        "payment.refunded",
        "payment",
        refund.id,
        {"order_number": order.order_number, "source_payment_id": source_payment.id, "amount": money(amount)},
    )
    response_body = {"data": refund.to_dict(), "order": order.to_dict()}
    _finish_idempotent_mutation(idempotency_record, response_body, 201)
    _commit()
    return jsonify(response_body), 201


@api_bp.get("/reports/sales")
@role_required("admin", "manager")
def sales_report():
    """A simple date-bounded report for managerial review and export clients."""
    query = Order.query.filter(Order.status == "completed")
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    from_boundary = _report_date_boundary(date_from) if date_from else None
    to_boundary = _report_date_boundary(date_to, exclusive_end=True) if date_to else None
    if from_boundary is not None and to_boundary is not None and from_boundary >= to_boundary:
        raise APIError(
            "The report start date must be on or before the end date.",
            details={"from/to": "invalid date range"},
        )
    if from_boundary is not None:
        query = query.filter(Order.completed_at >= from_boundary)
    if to_boundary is not None:
        query = query.filter(Order.completed_at < to_boundary)
    gross_sales = query.with_entities(func.coalesce(func.sum(Order.total_amount), 0)).scalar() or Decimal("0.00")
    net_revenue = _net_payment_total(query)
    count = query.count()
    by_status = {status: Order.query.filter_by(status=status).count() for status in ORDER_STATUSES}
    return jsonify(
        {
            "data": {
                "completed_order_count": count,
                "revenue": money(net_revenue),
                "gross_sales": money(gross_sales),
                "orders_by_status": by_status,
            }
        }
    )


@api_bp.get("/audit-logs")
@role_required("admin")
def audit_logs():
    page, per_page = page_args(request)
    return jsonify(paginated(AuditLog.query.order_by(AuditLog.created_at.desc()), page, per_page, lambda log: log.to_dict()))
