"""Flask application factory and consistent API error handling."""

from __future__ import annotations

from pathlib import Path

import click
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException, NotFound

from config import Config

from .auth import auth_bp
from .extensions import db, jwt, migrate
from .models import AuditLog, SessionBlocklist, TokenBlocklist, User
from .resources import api_bp
from .utils import APIError, error_response


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Config.validate_runtime(app.config)

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    # The bundled dashboard is same-origin by default. Supply allowed origins via
    # CORS_ORIGINS only when deploying the frontend separately.
    cors_origins = app.config.get("CORS_ORIGINS")
    if cors_origins:
        CORS(
            app,
            resources={r"/api/*": {"origins": cors_origins}},
            supports_credentials=True,
            allow_headers=["Content-Type", "Authorization", "X-CSRF-TOKEN"],
        )

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    _register_error_handlers(app)
    _register_jwt_handlers(app)
    _register_cli(app)
    _register_frontend(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        db.session.rollback()
        return error_response(error)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        db.session.rollback()
        return jsonify({"error": {"code": error.name.lower().replace(" ", "_"), "message": error.description}}), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        db.session.rollback()
        app.logger.exception("Unhandled application error", exc_info=error)
        return jsonify({"error": {"code": "internal_error", "message": "An unexpected error occurred."}}), 500


def _register_jwt_handlers(app: Flask) -> None:
    @jwt.token_in_blocklist_loader
    def is_token_blocked(_jwt_header, jwt_payload) -> bool:
        if TokenBlocklist.query.filter_by(jti=jwt_payload["jti"]).first() is not None:
            return True
        session_id = jwt_payload.get("sid")
        if session_id and SessionBlocklist.query.filter_by(session_id=session_id).first() is not None:
            return True
        user = db.session.get(User, int(jwt_payload["sub"]))
        return not user or not user.is_active or jwt_payload.get("sv") != user.session_version

    @jwt.unauthorized_loader
    def missing_token(reason: str):
        return jsonify({"error": {"code": "authorization_required", "message": reason}}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason: str):
        return jsonify({"error": {"code": "invalid_token", "message": reason}}), 422

    @jwt.expired_token_loader
    def expired_token(_jwt_header, _jwt_payload):
        return jsonify({"error": {"code": "token_expired", "message": "Your session has expired. Please sign in again."}}), 401

    @jwt.revoked_token_loader
    def revoked_token(_jwt_header, _jwt_payload):
        return jsonify({"error": {"code": "token_revoked", "message": "This session has been signed out."}}), 401


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed-local-admin")
    def seed_local_admin() -> None:
        """Create the fixed administrator only for a local SQLite development database."""
        if app.config.get("ENVIRONMENT") != "development" or db.engine.dialect.name != "sqlite":
            raise click.ClickException(
                "seed-local-admin is available only with APP_ENV=development on a local SQLite database."
            )

        seed_email = app.config["LOCAL_DEVELOPMENT_ADMIN_EMAIL"]
        existing_admin = User.query.filter_by(role="admin", is_active=True).first()
        if existing_admin:
            click.echo(f"An active administrator already exists ({existing_admin.email}); local seed unchanged.")
            return

        # Never alter an account that happens to use the fixed local address.
        # This makes repeats harmless and avoids resetting an intentionally
        # changed password or role in a developer's working database.
        if User.query.filter_by(email=seed_email).first():
            click.echo("The local administrator email is already in use; local seed unchanged.")
            return

        user = User(
            full_name=app.config["LOCAL_DEVELOPMENT_ADMIN_NAME"],
            email=seed_email,
            role="admin",
        )
        user.set_password(app.config["LOCAL_DEVELOPMENT_ADMIN_PASSWORD"])
        db.session.add(user)
        try:
            db.session.flush()
            db.session.add(
                AuditLog(
                    actor_user_id=user.id,
                    action="user.created",
                    entity_type="user",
                    entity_id=str(user.id),
                    details={"email": user.email, "role": "admin", "source": "local_development_seed"},
                )
            )
            db.session.commit()
        except IntegrityError:
            # A second local shell may have seeded at the same time. Treat a
            # successful competing seed as the same idempotent outcome.
            db.session.rollback()
            if User.query.filter_by(role="admin", is_active=True).first():
                click.echo("An active administrator already exists; local seed unchanged.")
                return
            raise click.ClickException("Could not create the local administrator.")
        except Exception as error:
            db.session.rollback()
            raise click.ClickException(f"Could not create the local administrator: {error}")

        click.echo(f"Created local development administrator {user.email}.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Administrator name")
    @click.option("--email", prompt="Administrator email")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(name: str, email: str, password: str) -> None:
        """Safely provision the first owner without exposing a public endpoint."""
        name = name.strip()
        email = email.strip().lower()
        if not name or "@" not in email or len(password) < 10:
            raise click.ClickException("Provide a name, valid email, and password of at least 10 characters.")
        if db.engine.dialect.name == "postgresql":
            # One transaction-wide advisory lock prevents two release jobs from
            # creating competing first administrators.
            db.session.execute(text("SELECT pg_advisory_xact_lock(76421491)"))
        if User.query.count() > 0:
            raise click.ClickException("An account already exists; initial admin creation is closed.")

        user = User(full_name=name, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.flush()
            db.session.add(
                AuditLog(
                    actor_user_id=user.id,
                    action="user.created",
                    entity_type="user",
                    entity_id=str(user.id),
                    details={"email": user.email, "role": "admin", "source": "deployment_cli"},
                )
            )
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            raise click.ClickException(f"Could not create administrator: {error}")
        click.echo(f"Created administrator {user.email}.")

    @app.cli.command("init-db")
    def init_db() -> None:
        """Create tables for local development. Use Alembic migrations in production."""
        db.create_all()
        print("Database tables are ready.")

    @app.cli.command("purge-expired-tokens")
    def purge_expired_tokens() -> None:
        """Remove expired token revocations; schedule this daily in production."""
        from .models import utc_now

        removed_tokens = TokenBlocklist.query.filter(TokenBlocklist.expires_at < utc_now()).delete()
        removed_sessions = SessionBlocklist.query.filter(SessionBlocklist.expires_at < utc_now()).delete()
        db.session.commit()
        print(f"Removed {removed_tokens} token records and {removed_sessions} session records.")

    @app.cli.command("seed-demo-data")
    def seed_demo_data() -> None:
        """Seed realistic artisan cakes with photos, customer profiles, and orders for testing."""
        from decimal import Decimal
        from .models import Customer, InventoryMovement, Order, OrderItem, OrderStatusEvent, Payment, Product, utc_now

        admin = User.query.filter_by(role="admin").first()
        if not admin:
            click.echo("Please seed or create an admin first (e.g. flask --app run:app seed-local-admin).")
            return

        if Product.query.count() > 0:
            click.echo("Products already exist. Demo seed skipped.")
            return

        demo_products = [
            {
                "sku": "TRF-01",
                "name": "Belgian Dark Chocolate Truffle",
                "category": "Chocolate",
                "description": "70% single-origin Callebaut ganache layered with moist cocoa sponge and chocolate mirror glaze.",
                "unit_price": Decimal("1250.00"),
                "cost_price": Decimal("480.00"),
                "stock_quantity": 14,
                "reorder_level": 4,
                "image_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "RV-02",
                "name": "Red Velvet Raspberry Bloom",
                "category": "Signature cakes",
                "description": "Classic buttermilk sponge with Madagascar vanilla cream cheese frosting and fresh raspberry coulis.",
                "unit_price": Decimal("1100.00"),
                "cost_price": Decimal("420.00"),
                "stock_quantity": 8,
                "reorder_level": 3,
                "image_url": "https://images.unsplash.com/photo-1586788680434-30d324b2d46f?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "VAN-03",
                "name": "Madagascar Vanilla Bean & Berries",
                "category": "Signature cakes",
                "description": "Pure vanilla sponge topped with whipped white chocolate mousse and hand-picked macerated berries.",
                "unit_price": Decimal("950.00"),
                "cost_price": Decimal("350.00"),
                "stock_quantity": 16,
                "reorder_level": 5,
                "image_url": "https://images.unsplash.com/photo-1535141192574-5d4897c13136?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "ESP-04",
                "name": "Espresso Roasted Hazelnut Gateau",
                "category": "Chocolate",
                "description": "Arabica coffee-infused sponge, toasted Piedmont hazelnut praline, and dark espresso mousse.",
                "unit_price": Decimal("1350.00"),
                "cost_price": Decimal("520.00"),
                "stock_quantity": 6,
                "reorder_level": 3,
                "image_url": "https://images.unsplash.com/photo-1606890737304-57a1ca8a5b62?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "PST-05",
                "name": "Pistachio Rose Cardamom Entremet",
                "category": "Celebration",
                "description": "Iranian pistachio dacquoise with fragrant rose water cream, crushed cardamom, and edible silver leaf.",
                "unit_price": Decimal("1450.00"),
                "cost_price": Decimal("580.00"),
                "stock_quantity": 4,
                "reorder_level": 4,
                "image_url": "https://images.unsplash.com/photo-1565958011703-44f9829ba187?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "CAR-06",
                "name": "Salted Caramel Pecan Crunch",
                "category": "Celebration",
                "description": "Golden sponge layered with sea salt butterscotch, roasted buttery pecans, and whipped caramel cream.",
                "unit_price": Decimal("1200.00"),
                "cost_price": Decimal("460.00"),
                "stock_quantity": 9,
                "reorder_level": 3,
                "image_url": "https://images.unsplash.com/photo-1563729784474-d77dbb933a9e?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "LEM-07",
                "name": "Wild Blueberry Lemon Curd Tart Cake",
                "category": "Seasonal",
                "description": "Tangy zesty Meyer lemon curd layered with wild blueberry reduction and almond shortbread crumb.",
                "unit_price": Decimal("1050.00"),
                "cost_price": Decimal("390.00"),
                "stock_quantity": 7,
                "reorder_level": 3,
                "image_url": "https://images.unsplash.com/photo-1519869325930-281384150729?auto=format&fit=crop&w=600&q=80",
            },
            {
                "sku": "VGN-08",
                "name": "Dark Chocolate Avocado Fudge (Vegan)",
                "category": "Vegan",
                "description": "100% plant-based rich chocolate cake made with organic Hass avocado, coconut cream, and maple fudge.",
                "unit_price": Decimal("1150.00"),
                "cost_price": Decimal("440.00"),
                "stock_quantity": 5,
                "reorder_level": 3,
                "image_url": "https://images.unsplash.com/photo-1542826438-bd32f43d626f?auto=format&fit=crop&w=600&q=80",
            },
        ]

        products = []
        for pdata in demo_products:
            prod = Product(**pdata)
            db.session.add(prod)
            db.session.flush()
            db.session.add(
                InventoryMovement(
                    product_id=prod.id,
                    created_by_user_id=admin.id,
                    quantity_change=prod.stock_quantity,
                    reason="restock",
                    note="Initial bakery shelf setup.",
                )
            )
            products.append(prod)

        # Seed Customers
        c1 = Customer(
            full_name="Priya Sharma",
            email="priya.sharma@example.com",
            phone="+91 98201 44102",
            address="Flat 402, Green Glen Towers, Indiranagar, Bengaluru",
            notes="Prefers eggless options; loyal celebration cake buyer.",
        )
        c2 = Customer(
            full_name="Rohan Verma",
            email="rohan.v@example.com",
            phone="+91 98450 19283",
            address="12 Richmond Road, Ashok Nagar, Bengaluru",
            notes="Regular espresso gateau order on weekends.",
        )
        c3 = Customer(
            full_name="Ananya Sen",
            email="ananya.sen@example.com",
            phone="+91 97112 88471",
            address="Penthouse 8, Palm Meadows, Whitefield, Bengaluru",
            notes="Corporate order coordinator.",
        )
        db.session.add_all([c1, c2, c3])
        db.session.flush()

        # Seed Sample Orders
        # Order 1: Confirmed pickup order for Priya
        o1 = Order(
            order_number="BL-2026-0001",
            customer_id=c1.id,
            created_by_user_id=admin.id,
            status="confirmed",
            payment_status="paid",
            payment_method="upi",
            fulfillment_type="pickup",
            notes="Please write 'Happy 25th Rhea!' on Belgian Dark Chocolate Truffle.",
            subtotal=Decimal("2350.00"),
            discount_amount=Decimal("100.00"),
            total_amount=Decimal("2250.00"),
            stock_applied_at=utc_now(),
        )
        db.session.add(o1)
        db.session.flush()
        item1 = OrderItem(order_id=o1.id, product_id=products[0].id, product_name=products[0].name, unit_price=products[0].unit_price, quantity=1, line_total=products[0].unit_price)
        item2 = OrderItem(order_id=o1.id, product_id=products[1].id, product_name=products[1].name, unit_price=products[1].unit_price, quantity=1, line_total=products[1].unit_price)
        pay1 = Payment(order_id=o1.id, created_by_user_id=admin.id, amount=Decimal("2250.00"), method="upi", status="captured", provider_reference="UPI-9481729381")
        status_ev1 = OrderStatusEvent(order_id=o1.id, changed_by_user_id=admin.id, from_status="draft", to_status="confirmed", note="Confirmed at counter with full UPI payment.")
        db.session.add_all([item1, item2, pay1, status_ev1])

        # Order 2: In-Kitchen order for Rohan
        o2 = Order(
            order_number="BL-2026-0002",
            customer_id=c2.id,
            created_by_user_id=admin.id,
            status="in_progress",
            payment_status="paid",
            payment_method="card",
            fulfillment_type="delivery",
            delivery_address=c2.address,
            notes="Extra roasted hazelnut crunch on top.",
            subtotal=Decimal("1350.00"),
            total_amount=Decimal("1350.00"),
            stock_applied_at=utc_now(),
        )
        db.session.add(o2)
        db.session.flush()
        item3 = OrderItem(order_id=o2.id, product_id=products[3].id, product_name=products[3].name, unit_price=products[3].unit_price, quantity=1, line_total=products[3].unit_price)
        pay2 = Payment(order_id=o2.id, created_by_user_id=admin.id, amount=Decimal("1350.00"), method="card", status="captured", provider_reference="POS-AUTH-88219")
        status_ev2 = OrderStatusEvent(order_id=o2.id, changed_by_user_id=admin.id, from_status="confirmed", to_status="in_progress", note="Baking sponge and preparing praline.")
        db.session.add_all([item3, pay2, status_ev2])

        db.session.commit()
        click.echo(f"Seeded {len(products)} cakes, 3 customers, and 2 active orders.")


def _register_frontend(app: Flask) -> None:
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_dashboard(path: str):
        """Serve the built React SPA while leaving /api routes to blueprints."""
        if path == "api" or path.startswith("api/"):
            raise NotFound("API endpoint not found.")
        if not frontend_dir.exists():
            return jsonify(
                {
                    "message": "Cake Shop API is running. Build the React dashboard with `cd frontend && npm run build` to serve it here."
                }
            ), 503
        requested = frontend_dir / path
        if path and requested.is_file():
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "index.html")
