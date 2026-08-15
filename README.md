<div align="center">

# 🍰 Butterlane
### Artisanal Bakery Operations & Point-of-Sale Platform

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel%20App-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://cake-shop-management-five.vercel.app/)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Aiven%20Cloud-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://aiven.io/)

<br />

**[🌐 Experience the Live Application](https://cake-shop-management-five.vercel.app/)**

| Access Role | Email | Password |
| :--- | :--- | :--- |
| **Administrator** | `admin@butterlane.local` | `ButterlaneLocal2026!` |
| **Store Owner** | `owner@butterlane.local` | `ButterlaneAdmin2026!` |

</div>

---

## 📸 Interface Preview

<div align="center">
  <img src="docs/screenshots/inventory-dashboard.png" alt="Butterlane Inventory Dashboard" width="90%" style="border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);" />
  <p><em>Real-time Bakery Inventory Ledger, Stock Health Indicators & Operational Kitchen Pulse</em></p>

  <br />

  <img src="docs/screenshots/stock-adjustment.png" alt="Stock Adjustment Modal" width="90%" style="border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);" />
  <p><em>Audited Stock Adjustment & Restocking Dialogue with Traceable Notes</em></p>
</div>

---

## ✨ Highlights & Capabilities

* **⚡ Point-of-Sale (POS) & Counter Billing:** Rapid cake ordering interface with product photography, customizable discount rules, tax computation, and receipt generation formatted with dedicated print styling (`@media print`).
* **📦 Kitchen Fulfillment Pipeline:** Live state machine tracking orders across `Draft` ➔ `Confirmed` ➔ `In Progress` ➔ `Ready` ➔ `Completed`, supporting both takeaway pickups and timed deliveries.
* **🛡️ Immutable Stock Ledger:** Confirmed orders reserve stock under database row locks. Cancellations restore inventory, and manual adjustments record user-attributed audit logs.
* **👥 Customer Relationship Management:** Detailed customer profiles with contact records, notes, past order receipts, and real-time lifetime spend analytics.
* **🔐 Enterprise Financial Safety:** Transactional payment capture (UPI, Card, Cash) and refunds enforce `Idempotency-Key` headers to prevent double-charging over flaky networks.
* **🍪 Production Authentication:** Stateless access tokens paired with rotated HTTP-only refresh cookies (`SameSite=Lax`, `Secure`), scrypt password hashing, and active session blocklists.

---

## 🛠️ Architecture & Tech Stack

```
CakeShopManagement/
├── backend/                  # Flask RESTful API & Domain Layer
│   ├── app/                  # Application Factory, Blueprints & Models
│   ├── migrations/           # Alembic Schema Migrations
│   ├── config.py             # Environment & Database Configuration
│   └── run.py                # Development Runner
├── frontend/                 # React 19 Single Page Application
│   ├── src/                  # Components, Contexts, Pages & Custom Hooks
│   ├── index.html            # SPA Entrypoint
│   └── vite.config.js        # Vite Build Configuration
├── scripts/                  # Build & Remote DB Management Utilities
├── database_schema.sql       # Standalone PostgreSQL DDL & Seed Script
├── vercel.json               # Vercel Serverless Function & Edge Routing
└── index.py                  # Vercel WSGI Serverless Entrypoint
```

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, Vite, Impeccable Design Tokens, CSS Modules |
| **Backend** | Python 3.13, Flask 3.0, Flask-SQLAlchemy 3.1, Flask-JWT-Extended, Flask-Migrate |
| **Database** | Managed PostgreSQL on [Aiven Cloud](https://aiven.io/), psycopg 3 binary |
| **Deployment** | [Vercel](https://vercel.com) Serverless Functions + Global Edge CDN |

---

## 🚀 Quick Start (Local Development)

### 1. Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

# Run database migrations and start debug server
flask --app run:app db upgrade
flask --app run:app seed-local-admin
flask --app run:app run --debug
```

### 2. Frontend Setup
In a separate terminal:
```bash
cd frontend
npm ci
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

### 3. Run Automated Tests
```bash
cd backend
python -m pytest -q
# Output: 22 passed in 3.19s
```

---

## 🌐 Production Deployment

### Database (Aiven PostgreSQL)
1. Provision a PostgreSQL service in [Aiven](https://console.aiven.io/).
2. Initialize and seed the remote database in one command:
   ```bash
   python scripts/setup-remote-db.py "<AIVEN_SERVICE_URI>"
   ```

### Hosting (Vercel)
Import the repository into [Vercel](https://vercel.com) and configure these Environment Variables:

| Variable | Recommended Production Value |
| :--- | :--- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | `postgres://avnadmin:PASSWORD@HOST:PORT/defaultdb?sslmode=require` |
| `DB_SSLMODE` | `require` |
| `SECRET_KEY` | *Minimum 32-character cryptographically random secret* |
| `JWT_SECRET_KEY` | *Distinct 32-character random secret* |
| `JWT_COOKIE_SECURE` | `true` |
| `JWT_COOKIE_SAMESITE` | `Lax` |
| `SHOP_TIMEZONE` | `Asia/Kolkata` *(or your local IANA timezone)* |

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
