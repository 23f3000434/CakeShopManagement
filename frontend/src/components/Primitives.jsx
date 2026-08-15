import { memo } from "react";
import { Icon } from "./Icon";

export function GlassPanel({ children, className = "", padding = true }) {
  return <section className={`glass-panel ${padding ? "glass-panel--padded" : ""} ${className}`}>{children}</section>;
}

export const MetricCard = memo(function MetricCard({ label, value, caption, tone = "rose", icon }) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <div className="metric-card__label"><span>{label}</span><span className="metric-card__icon"><Icon name={icon} size={15} /></span></div>
      <strong className="metric-card__value">{value}</strong>
      <span className="metric-card__caption">{caption}</span>
    </article>
  );
});

export function StatusPill({ status, children }) {
  const normalized = String(status || "draft").toLowerCase().replaceAll("_", "-");
  return <span className={`status-pill status-pill--${normalized}`}>{children || String(status || "draft").replaceAll("_", " ")}</span>;
}

export function PageHeading({ description }) {
  return (
    <div className="page-intro page-intro--compact">
      <div>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}

export function EmptyState({ icon = "sparkle", title, description, action }) {
  return <div className="empty-state"><span className="empty-state__icon"><Icon name={icon} size={24} /></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function LoadingPanel({ label = "Loading bakery records…" }) {
  return <div className="loading-panel"><span className="loading-panel__orb" /><span>{label}</span></div>;
}

export function Avatar({ name = "Butterlane", size = "default" }) {
  const initials = name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "BL";
  return <span className={`avatar avatar--${size}`}>{initials}</span>;
}
