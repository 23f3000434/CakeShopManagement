BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 084747508c2d

CREATE TABLE customers (
    id SERIAL NOT NULL, 
    full_name VARCHAR(160) NOT NULL, 
    email VARCHAR(255), 
    phone VARCHAR(32), 
    address TEXT, 
    notes TEXT, 
    is_active BOOLEAN NOT NULL, 
    total_spent NUMERIC(12, 2) NOT NULL, 
    completed_order_count INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_customers_email ON customers (email);

CREATE INDEX ix_customers_full_name ON customers (full_name);

CREATE INDEX ix_customers_phone ON customers (phone);

CREATE TABLE products (
    id SERIAL NOT NULL, 
    sku VARCHAR(64) NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    category VARCHAR(80) NOT NULL, 
    description TEXT, 
    unit_price NUMERIC(12, 2) NOT NULL, 
    cost_price NUMERIC(12, 2), 
    stock_quantity INTEGER NOT NULL, 
    reorder_level INTEGER NOT NULL, 
    image_url VARCHAR(500), 
    is_active BOOLEAN NOT NULL, 
    version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_products_category ON products (category);

CREATE INDEX ix_products_name ON products (name);

CREATE UNIQUE INDEX ix_products_sku ON products (sku);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    full_name VARCHAR(120) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    session_version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE idempotency_records (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    endpoint VARCHAR(240) NOT NULL, 
    key VARCHAR(128) NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    status_code INTEGER, 
    response_body JSON, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    CONSTRAINT uq_idempotency_user_endpoint_key UNIQUE (user_id, endpoint, key)
);

CREATE INDEX ix_idempotency_records_created_at ON idempotency_records (created_at);

CREATE INDEX ix_idempotency_records_expires_at ON idempotency_records (expires_at);

CREATE INDEX ix_idempotency_records_user_id ON idempotency_records (user_id);

CREATE TABLE audit_logs (
    id SERIAL NOT NULL, 
    actor_user_id INTEGER, 
    action VARCHAR(80) NOT NULL, 
    entity_type VARCHAR(80) NOT NULL, 
    entity_id VARCHAR(64) NOT NULL, 
    details JSON, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_actor_user_id ON audit_logs (actor_user_id);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX ix_audit_logs_entity_id ON audit_logs (entity_id);

CREATE INDEX ix_audit_logs_entity_type ON audit_logs (entity_type);

CREATE TABLE orders (
    id SERIAL NOT NULL, 
    order_number VARCHAR(32) NOT NULL, 
    customer_id INTEGER, 
    created_by_user_id INTEGER NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    payment_status VARCHAR(24) NOT NULL, 
    payment_method VARCHAR(40), 
    fulfillment_type VARCHAR(24) NOT NULL, 
    pickup_at TIMESTAMP WITH TIME ZONE, 
    delivery_address TEXT, 
    notes TEXT, 
    subtotal NUMERIC(12, 2) NOT NULL, 
    discount_amount NUMERIC(12, 2) NOT NULL, 
    tax_rate NUMERIC(5, 2) NOT NULL, 
    tax_amount NUMERIC(12, 2) NOT NULL, 
    total_amount NUMERIC(12, 2) NOT NULL, 
    stock_applied_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE INDEX ix_orders_completed_at ON orders (completed_at);

CREATE INDEX ix_orders_customer_id ON orders (customer_id);

CREATE UNIQUE INDEX ix_orders_order_number ON orders (order_number);

CREATE INDEX ix_orders_pickup_at ON orders (pickup_at);

CREATE INDEX ix_orders_status ON orders (status);

CREATE TABLE session_blocklist (
    id SERIAL NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    user_id INTEGER NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_session_blocklist_session_id ON session_blocklist (session_id);

CREATE INDEX ix_session_blocklist_user_id ON session_blocklist (user_id);

CREATE TABLE token_blocklist (
    id SERIAL NOT NULL, 
    jti VARCHAR(36) NOT NULL, 
    token_type VARCHAR(10) NOT NULL, 
    user_id INTEGER NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_token_blocklist_jti ON token_blocklist (jti);

CREATE TABLE inventory_movements (
    id SERIAL NOT NULL, 
    product_id INTEGER NOT NULL, 
    order_id INTEGER, 
    created_by_user_id INTEGER NOT NULL, 
    quantity_change INTEGER NOT NULL, 
    reason VARCHAR(32) NOT NULL, 
    note VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(order_id) REFERENCES orders (id), 
    FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE INDEX ix_inventory_movements_created_at ON inventory_movements (created_at);

CREATE INDEX ix_inventory_movements_order_id ON inventory_movements (order_id);

CREATE INDEX ix_inventory_movements_product_id ON inventory_movements (product_id);

CREATE TABLE order_items (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    product_id INTEGER, 
    product_name VARCHAR(160) NOT NULL, 
    unit_price NUMERIC(12, 2) NOT NULL, 
    quantity INTEGER NOT NULL, 
    line_total NUMERIC(12, 2) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(order_id) REFERENCES orders (id), 
    FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE INDEX ix_order_items_order_id ON order_items (order_id);

CREATE INDEX ix_order_items_product_id ON order_items (product_id);

CREATE TABLE order_status_events (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    changed_by_user_id INTEGER NOT NULL, 
    from_status VARCHAR(24), 
    to_status VARCHAR(24) NOT NULL, 
    note VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(changed_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(order_id) REFERENCES orders (id)
);

CREATE INDEX ix_order_status_events_order_id ON order_status_events (order_id);

CREATE TABLE payments (
    id SERIAL NOT NULL, 
    order_id INTEGER NOT NULL, 
    created_by_user_id INTEGER NOT NULL, 
    amount NUMERIC(12, 2) NOT NULL, 
    method VARCHAR(40) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    refunded_payment_id INTEGER, 
    provider_reference VARCHAR(160), 
    note VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(order_id) REFERENCES orders (id), 
    FOREIGN KEY(refunded_payment_id) REFERENCES payments (id), 
    UNIQUE (provider_reference)
);

CREATE INDEX ix_payments_refunded_payment_id ON payments (refunded_payment_id);

CREATE INDEX ix_payments_order_id ON payments (order_id);

INSERT INTO alembic_version (version_num) VALUES ('084747508c2d') ON CONFLICT DO NOTHING;

-- ==========================================================
-- Initial Default Administrator
-- Email:    admin@butterlane.local
-- Password: ButterlaneLocal2026!
-- ==========================================================
INSERT INTO users (full_name, email, password_hash, role, is_active, session_version, created_at, updated_at)
VALUES (
    'Butterlane Administrator',
    'admin@butterlane.local',
    'scrypt:32768:8:1$0N14lfdwTPD4x8Qm$36df3947e3387f5a2e68b36eb25cde99b21d5894a635c4335476f2cd7536a8605b7cb6bff9c5316b9af904ac3840471527c59da18f91ce1dc89e91d816d36532',
    'admin',
    true,
    1,
    NOW(),
    NOW()
) ON CONFLICT (email) DO NOTHING;


-- ==========================================================
-- Initial Demo Products (Bakery Catalogue)
-- ==========================================================
INSERT INTO products (sku, name, category, description, unit_price, cost_price, stock_quantity, reorder_level, image_url, is_active, version, created_at, updated_at)
VALUES
('TRF-01', 'Belgian Dark Chocolate Truffle', 'Chocolate', '70% single-origin Callebaut ganache layered with moist cocoa sponge and chocolate mirror glaze.', 1250.00, 480.00, 14, 4, 'https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('RV-02', 'Red Velvet Raspberry Bloom', 'Signature cakes', 'Classic buttermilk sponge with Madagascar vanilla cream cheese frosting and fresh raspberry coulis.', 1100.00, 420.00, 8, 3, 'https://images.unsplash.com/photo-1586788680434-30d324b2d46f?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('VAN-03', 'Madagascar Vanilla Bean & Berries', 'Signature cakes', 'Pure vanilla sponge topped with whipped white chocolate mousse and hand-picked macerated berries.', 950.00, 350.00, 16, 5, 'https://images.unsplash.com/photo-1535141192574-5d4897c13136?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('ESP-04', 'Espresso Roasted Hazelnut Gateau', 'Chocolate', 'Arabica coffee-infused sponge, toasted Piedmont hazelnut praline, and dark espresso mousse.', 1350.00, 520.00, 6, 3, 'https://images.unsplash.com/photo-1606890737304-57a1ca8a5b62?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('PST-05', 'Pistachio Rose Cardamom Entremet', 'Celebration', 'Iranian pistachio dacquoise with fragrant rose water cream, crushed cardamom, and edible silver leaf.', 1450.00, 580.00, 4, 4, 'https://images.unsplash.com/photo-1565958011703-44f9829ba187?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('CAR-06', 'Salted Caramel Pecan Crunch', 'Celebration', 'Golden sponge layered with sea salt butterscotch, roasted buttery pecans, and whipped caramel cream.', 1200.00, 460.00, 9, 3, 'https://images.unsplash.com/photo-1563729784474-d77dbb933a9e?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('LEM-07', 'Wild Blueberry Lemon Curd Tart Cake', 'Seasonal', 'Tangy zesty Meyer lemon curd layered with wild blueberry reduction and almond shortbread crumb.', 1050.00, 390.00, 7, 3, 'https://images.unsplash.com/photo-1519869325930-281384150729?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW()),
('VGN-08', 'Dark Chocolate Avocado Fudge (Vegan)', 'Vegan', '100% plant-based rich chocolate cake made with organic Hass avocado, coconut cream, and maple fudge.', 1150.00, 440.00, 5, 3, 'https://images.unsplash.com/photo-1542826438-bd32f43d626f?auto=format&fit=crop&w=600&q=80', true, 1, NOW(), NOW())
ON CONFLICT (sku) DO NOTHING;

COMMIT;

