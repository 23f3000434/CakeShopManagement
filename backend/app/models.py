"""Database models for people, catalogue, orders, and stock audit history."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def money(value: Decimal | int | float | None) -> float:
    return float(value or 0)


def timestamp_isoformat(value: datetime | None) -> str | None:
    """Serialize UTC timestamps consistently across PostgreSQL and SQLite.

    PostgreSQL round-trips timezone-aware values, while SQLite returns the
    UTC timestamps written by this application without tzinfo.  A bare ISO
    string is interpreted in the browser's local timezone, so restore UTC
    before returning it from the API.
    """
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)

    orders = db.relationship("Order", back_populates="created_by", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": timestamp_isoformat(self.created_at),
        }


class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    token_type = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)


class SessionBlocklist(db.Model):
    """Revokes an entire refresh-token family after logout or account action."""

    __tablename__ = "session_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    user = db.relationship("User")


class IdempotencyRecord(db.Model):
    """Caches a completed financial mutation so a retry cannot charge twice."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        db.UniqueConstraint("user_id", "endpoint", "key", name="uq_idempotency_user_endpoint_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    endpoint = db.Column(db.String(240), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)

    user = db.relationship("User")


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    phone = db.Column(db.String(32), nullable=True, index=True)
    address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    total_spent = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    completed_order_count = db.Column(db.Integer, nullable=False, default=0)

    orders = db.relationship("Order", back_populates="customer", lazy="dynamic")

    def to_dict(self, include_orders: bool = False) -> dict:
        result = {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "notes": self.notes,
            "is_active": self.is_active,
            "total_spent": money(self.total_spent),
            "completed_order_count": self.completed_order_count,
            "created_at": timestamp_isoformat(self.created_at),
            "updated_at": timestamp_isoformat(self.updated_at),
        }
        if include_orders:
            result["orders"] = [order.to_dict(include_items=False) for order in self.orders.order_by(Order.created_at.desc())]
        return result


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False, default="Cakes", index=True)
    description = db.Column(db.Text, nullable=True)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    cost_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    reorder_level = db.Column(db.Integer, nullable=False, default=5)
    image_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)

    order_items = db.relationship("OrderItem", back_populates="product")
    stock_movements = db.relationship("InventoryMovement", back_populates="product", lazy="dynamic")

    # Protect against lost updates in multi-worker PostgreSQL deployments.
    __mapper_args__ = {"version_id_col": version}

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.reorder_level

    def to_dict(self, *, include_cost_price: bool = False) -> dict:
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "unit_price": money(self.unit_price),
            **(
                {"cost_price": money(self.cost_price) if self.cost_price is not None else None}
                if include_cost_price
                else {}
            ),
            "stock_quantity": self.stock_quantity,
            "reorder_level": self.reorder_level,
            "is_low_stock": self.is_low_stock,
            "image_url": self.image_url,
            "is_active": self.is_active,
            "version": self.version,
            "created_at": timestamp_isoformat(self.created_at),
            "updated_at": timestamp_isoformat(self.updated_at),
        }


class Order(TimestampMixin, db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    payment_status = db.Column(db.String(24), nullable=False, default="unpaid")
    payment_method = db.Column(db.String(40), nullable=True)
    fulfillment_type = db.Column(db.String(24), nullable=False, default="pickup")
    pickup_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    delivery_address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    stock_applied_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)

    customer = db.relationship("Customer", back_populates="orders")
    created_by = db.relationship("User", back_populates="orders")
    items = db.relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    inventory_movements = db.relationship("InventoryMovement", back_populates="order", lazy="dynamic")
    payments = db.relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    status_events = db.relationship(
        "OrderStatusEvent", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    __mapper_args__ = {"version_id_col": version}

    def to_dict(self, include_items: bool = True) -> dict:
        result = {
            "id": self.id,
            "order_number": self.order_number,
            "customer_id": self.customer_id,
            "customer": {"id": self.customer.id, "full_name": self.customer.full_name, "phone": self.customer.phone}
            if self.customer
            else None,
            "created_by": self.created_by.to_dict() if self.created_by else None,
            "status": self.status,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "fulfillment_type": self.fulfillment_type,
            "pickup_at": timestamp_isoformat(self.pickup_at),
            "delivery_address": self.delivery_address,
            "notes": self.notes,
            "subtotal": money(self.subtotal),
            "discount_amount": money(self.discount_amount),
            "tax_rate": money(self.tax_rate),
            "tax_amount": money(self.tax_amount),
            "total_amount": money(self.total_amount),
            "completed_at": timestamp_isoformat(self.completed_at),
            "version": self.version,
            "created_at": timestamp_isoformat(self.created_at),
            "updated_at": timestamp_isoformat(self.updated_at),
        }
        if include_items:
            result["items"] = [item.to_dict() for item in self.items]
            result["payments"] = [payment.to_dict() for payment in self.payments]
            result["status_events"] = [event.to_dict() for event in self.status_events]
        return result


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True, index=True)
    product_name = db.Column(db.String(160), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "unit_price": money(self.unit_price),
            "quantity": self.quantity,
            "line_total": money(self.line_total),
            "image_url": self.product.image_url if self.product else None,
        }


class InventoryMovement(db.Model):
    __tablename__ = "inventory_movements"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(32), nullable=False)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    product = db.relationship("Product", back_populates="stock_movements")
    order = db.relationship("Order", back_populates="inventory_movements")
    created_by = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "order_id": self.order_id,
            "order_number": self.order.order_number if self.order else None,
            "quantity_change": self.quantity_change,
            "reason": self.reason,
            "note": self.note,
            "created_by": self.created_by.full_name if self.created_by else None,
            "created_at": timestamp_isoformat(self.created_at),
        }


class Payment(db.Model):
    """Payment ledger. Provider references only—never raw card data."""

    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="captured")
    refunded_payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=True, index=True)
    provider_reference = db.Column(db.String(160), nullable=True, unique=True)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    order = db.relationship("Order", back_populates="payments")
    created_by = db.relationship("User")
    refunded_payment = db.relationship("Payment", remote_side=[id], backref="refunds")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "amount": money(self.amount),
            "method": self.method,
            "status": self.status,
            "refunded_payment_id": self.refunded_payment_id,
            "provider_reference": self.provider_reference,
            "note": self.note,
            "created_by": self.created_by.full_name if self.created_by else None,
            "created_at": timestamp_isoformat(self.created_at),
        }


class OrderStatusEvent(db.Model):
    """Immutable timeline that makes operational handoffs traceable."""

    __tablename__ = "order_status_events"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    from_status = db.Column(db.String(24), nullable=True)
    to_status = db.Column(db.String(24), nullable=False)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    order = db.relationship("Order", back_populates="status_events")
    changed_by = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "note": self.note,
            "changed_by": self.changed_by.full_name if self.changed_by else None,
            "created_at": timestamp_isoformat(self.created_at),
        }


class AuditLog(db.Model):
    """Small immutable audit stream for sensitive business actions."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.String(64), nullable=False, index=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    actor = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "actor": self.actor.full_name if self.actor else "System",
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "created_at": timestamp_isoformat(self.created_at),
        }
