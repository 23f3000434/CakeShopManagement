import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { Icon } from "../components/Icon";

const ADMIN_CREDENTIALS = import.meta.env.DEV ? {
  email: "admin@butterlane.local",
  password: "ButterlaneLocal2026!"
} : { email: "", password: "" };

function fieldMessage(error, field) {
  return error?.details?.[field] || "";
}

export default function AuthScreen() {
  const { login } = useAuth();
  const [values, setValues] = useState({
    email: ADMIN_CREDENTIALS.email,
    password: ADMIN_CREDENTIALS.password
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const emailRef = useRef(null);

  useEffect(() => emailRef.current?.focus(), []);

  const update = (event) => setValues((current) => ({ ...current, [event.target.name]: event.target.value }));

  const fillAdmin = () => {
    setValues({
      email: ADMIN_CREDENTIALS.email,
      password: ADMIN_CREDENTIALS.password
    });
    setError(null);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!values.email.trim() || !values.password) {
      setError(new ApiError("Enter both work email and password."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(values);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason : new ApiError("Something prevented sign-in. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-screen">
      <div className="auth-screen__ambient auth-screen__ambient--rose" aria-hidden="true" />
      <div className="auth-screen__ambient auth-screen__ambient--yellow" aria-hidden="true" />
      <section className="auth-card glass-panel">
        <div className="auth-card__story">
          <div className="brand brand--light">
            <span className="brand__mark">B</span>
            <span><strong>Butterlane</strong><small>Cake Atelier & Operations</small></span>
          </div>

          <div className="auth-card__copy">
            <h1>Artisan cakes, structured billing.</h1>
            <p>Direct counter POS, visual cake catalogue, kitchen fulfilment pipeline, and auditable stock control.</p>
          </div>

          <div className="auth-card__highlights">
            <div className="auth-highlight-item">
              <span className="auth-highlight-icon"><Icon name="receipt" size={15} /></span>
              <div>
                <strong>Point of Sale & Billing</strong>
                <span>Instant visual order billing with product photography and receipts.</span>
              </div>
            </div>
            <div className="auth-highlight-item">
              <span className="auth-highlight-icon"><Icon name="cake" size={15} /></span>
              <div>
                <strong>Inventory Ledger</strong>
                <span>Real-time stock deduction, restock tracking, and zero lost counts.</span>
              </div>
            </div>
          </div>
        </div>

        <div className="auth-card__form-side">
          <div className="auth-card__form-head">
            <h2>Sign in to Butterlane</h2>
            <p>Access the counter POS, kitchen queue, and bakery records.</p>
          </div>

          {/* Quick Admin Access Bar */}
          {import.meta.env.DEV && <div className="admin-credentials-banner">
            <div className="admin-credentials-badge">
              <Icon name="check" size={14} />
              <div>
                <strong>Default Admin Access</strong>
                <span><code>{ADMIN_CREDENTIALS.email}</code></span>
              </div>
            </div>
            <button
              type="button"
              className="button button--secondary button--small admin-fill-button"
              onClick={fillAdmin}
              title="Click to fill administrator credentials"
            >
              Fill Credentials
            </button>
          </div>}

          <form className="auth-form" onSubmit={submit} noValidate>
            <label className="form-field">
              <span>Work email</span>
              <input
                ref={emailRef}
                name="email"
                type="email"
                value={values.email}
                onChange={update}
                placeholder="you@yourbakery.com"
                autoComplete="email"
              />
              {fieldMessage(error, "email") ? <small>{fieldMessage(error, "email")}</small> : null}
            </label>
            <label className="form-field">
              <span>Password</span>
              <input
                name="password"
                type="password"
                value={values.password}
                onChange={update}
                placeholder="Your password"
                autoComplete="current-password"
              />
              {fieldMessage(error, "password") ? <small>{fieldMessage(error, "password")}</small> : null}
            </label>
            {error ? (
              <div className="form-error">
                <Icon name="alert" size={15} />
                <span>{error.message}</span>
              </div>
            ) : null}
            <button className="button button--primary auth-form__submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in to Counter"}
              <Icon name="arrowRight" size={16} />
            </button>
          </form>

          <p className="auth-card__security">
            <Icon name="check" size={14} /> Connected with PostgreSQL / SQLite operational ledger.
          </p>
        </div>
      </section>
    </main>
  );
}
