#!/usr/bin/env python3
"""Run schema migrations and seed initial data on a remote PostgreSQL database (such as Aiven).

Usage:
    python scripts/setup-remote-db.py "postgresql://avnadmin:PASSWORD@HOST:PORT/defaultdb?sslmode=require"
Or set DATABASE_URL in environment:
    export DATABASE_URL="postgresql://avnadmin:PASSWORD@HOST:PORT/defaultdb?sslmode=require"
    python scripts/setup-remote-db.py
"""

import os
import sys
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parents[1]
backend_dir = root_dir / "backend"
sys.path.insert(0, str(backend_dir))

if len(sys.argv) > 1 and sys.argv[1].startswith("postgres"):
    os.environ["DATABASE_URL"] = sys.argv[1]

if not os.getenv("DATABASE_URL"):
    print("Error: DATABASE_URL is not set.")
    print('Usage: python scripts/setup-remote-db.py "postgresql://avnadmin:PASSWORD@HOST:PORT/defaultdb?sslmode=require"')
    sys.exit(1)

os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("DB_SSLMODE", "require")
os.environ.setdefault("SECRET_KEY", "b8bfa932d3311eb6c30e53c5b9d45ad28fabb3339455549928cf223b7565d48b")
os.environ.setdefault("JWT_SECRET_KEY", "935589532f940c59bf7b1852f249dc61b33cb08116730df54b8468d012974356")
os.environ.setdefault("JWT_COOKIE_SECURE", "true")
os.environ.setdefault("SHOP_TIMEZONE", "Asia/Kolkata")

# Check if Aiven / remote host is ready, with automatic waiting while it builds
import socket
import time
from urllib.parse import urlsplit

db_url = os.environ["DATABASE_URL"]
parsed = urlsplit(db_url)
host = parsed.hostname
port = parsed.port or 5432

if host and host not in {"localhost", "127.0.0.1"}:
    print(f"Checking connectivity to {host}:{port}...")
    max_wait = 360
    start = time.time()
    connected = False
    while time.time() - start < max_wait:
        try:
            socket.getaddrinfo(host, port)
            with socket.create_connection((host, port), timeout=5):
                connected = True
                print(f"Connected successfully to {host}:{port}!")
                break
        except (socket.gaierror, socket.timeout, ConnectionRefusedError, OSError):
            elapsed = int(time.time() - start)
            print(f"Aiven service is still provisioning ({elapsed}s elapsed). Waiting for {host} to come online...")
            time.sleep(10)

    if not connected:
        print(f"Warning: Timed out waiting for {host}:{port}. Attempting connection anyway...")

from app import create_app
from app.extensions import db
from flask_migrate import upgrade

print("Connecting to remote database via SQLAlchemy...")
app = create_app()


with app.app_context():
    print("Running Alembic schema migrations...")
    upgrade(directory=str(backend_dir / "migrations"))
    print("Schema is up to date!")

    # Check / create default admin
    from app.models import User, Product
    admin = User.query.filter_by(role="admin").first()
    if not admin:
        print("Creating default administrator account...")
        admin = User(
            full_name="Butterlane Administrator",
            email="admin@butterlane.local",
            role="admin",
        )
        admin.set_password("ButterlaneAdmin2026!")
        db.session.add(admin)
        db.session.commit()
        print("Created default admin: admin@butterlane.local (password: ButterlaneAdmin2026!)")
    else:
        print(f"Admin account already exists: {admin.email}")

    # Seed demo products if empty
    if Product.query.count() == 0:
        print("Seeding artisan demo cakes...")
        from decimal import Decimal
        from app.models import InventoryMovement
        demo_products = [
            {"sku": "TRF-01", "name": "Belgian Dark Chocolate Truffle", "category": "Chocolate", "description": "70% single-origin Callebaut ganache layered with moist cocoa sponge.", "unit_price": Decimal("1250.00"), "cost_price": Decimal("480.00"), "stock_quantity": 14, "reorder_level": 4, "image_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80"},
            {"sku": "RV-02", "name": "Red Velvet Raspberry Bloom", "category": "Signature cakes", "description": "Classic buttermilk sponge with Madagascar vanilla cream cheese frosting.", "unit_price": Decimal("1100.00"), "cost_price": Decimal("420.00"), "stock_quantity": 8, "reorder_level": 3, "image_url": "https://images.unsplash.com/photo-1586788680434-30d324b2d46f?auto=format&fit=crop&w=600&q=80"},
            {"sku": "VAN-03", "name": "Madagascar Vanilla Bean & Berries", "category": "Signature cakes", "description": "Pure vanilla sponge topped with whipped white chocolate mousse.", "unit_price": Decimal("950.00"), "cost_price": Decimal("350.00"), "stock_quantity": 16, "reorder_level": 5, "image_url": "https://images.unsplash.com/photo-1535141192574-5d4897c13136?auto=format&fit=crop&w=600&q=80"},
            {"sku": "ESP-04", "name": "Espresso Roasted Hazelnut Gateau", "category": "Chocolate", "description": "Arabica coffee-infused sponge, toasted hazelnut praline, dark mousse.", "unit_price": Decimal("1350.00"), "cost_price": Decimal("520.00"), "stock_quantity": 6, "reorder_level": 3, "image_url": "https://images.unsplash.com/photo-1606890737304-57a1ca8a5b62?auto=format&fit=crop&w=600&q=80"},
            {"sku": "CAR-06", "name": "Salted Caramel Pecan Crunch", "category": "Celebration", "description": "Golden sponge layered with sea salt butterscotch, roasted pecans.", "unit_price": Decimal("1200.00"), "cost_price": Decimal("460.00"), "stock_quantity": 9, "reorder_level": 3, "image_url": "https://images.unsplash.com/photo-1563729784474-d77dbb933a9e?auto=format&fit=crop&w=600&q=80"},
        ]
        for pdata in demo_products:
            prod = Product(**pdata)
            db.session.add(prod)
            db.session.flush()
            db.session.add(InventoryMovement(product_id=prod.id, created_by_user_id=admin.id, quantity_change=prod.stock_quantity, reason="restock", note="Initial bakery shelf setup."))
        db.session.commit()
        print(f"Seeded {len(demo_products)} demo products.")
    else:
        print(f"Catalogue already has {Product.query.count()} products.")

print("\nDatabase is fully configured and ready for production!")
