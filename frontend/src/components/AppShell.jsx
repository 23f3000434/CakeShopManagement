import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { canManageOperations } from "../lib/permissions";
import { Icon } from "./Icon";
import { Avatar } from "./Primitives";

const navigation = [
  { id: "dashboard", label: "Overview", short: "Home", icon: "grid" },
  { id: "products", label: "Cakes & products", short: "Cakes", icon: "cake" },
  { id: "orders", label: "Orders", short: "Orders", icon: "receipt" },
  { id: "customers", label: "Customers", short: "People", icon: "users" },
  { id: "inventory", label: "Inventory", short: "Stock", icon: "package" }
];

const pageCopy = {
  dashboard: { eyebrow: "TODAY'S OPERATIONS", title: "Today’s work, in one view.", action: "New order" },
  products: { eyebrow: "CAKE CATALOGUE", title: "Manage what customers can order.", action: "New cake" },
  orders: { eyebrow: "FULFILMENT DESK", title: "Prepare every order on time.", action: "New order" },
  customers: { eyebrow: "CUSTOMER RECORDS", title: "Manage customer records.", action: "New customer" },
  inventory: { eyebrow: "STOCK CONTROL", title: "Review stock and restocking.", action: "Adjust stock" }
};

export function AppShell({ page, onNavigate, onQuickAction, search, onSearchChange, children, lowStockCount = 0, pendingOrderCount = 0 }) {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const searchRef = useRef(null);
  const copy = pageCopy[page] || pageCopy.dashboard;
  const canManage = canManageOperations(user);

  useEffect(() => setMenuOpen(false), [page]);
  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const statusNote = useMemo(() => {
    if (lowStockCount) return `${lowStockCount} low-stock alert${lowStockCount === 1 ? "" : "s"} needs a quick look.`;
    if (pendingOrderCount) return `${pendingOrderCount} orders are moving through the kitchen.`;
    return "Orders and stock are up to date.";
  }, [lowStockCount, pendingOrderCount]);

  const navigate = (next) => onNavigate(next);
  return (
    <div className="workspace">
      <div className={`sidebar-backdrop ${menuOpen ? "is-visible" : ""}`} onClick={() => setMenuOpen(false)} />
      <aside className={`sidebar glass-panel ${menuOpen ? "is-open" : ""}`} id="workspace-navigation" aria-label="Primary navigation">
        <div className="sidebar__brand-row">
          <button className="brand" onClick={() => navigate("dashboard")} aria-label="Go to dashboard">
            <span className="brand__mark">B</span><span><strong>Butterlane</strong><small>Cake shop operations</small></span>
          </button>
          <button className="icon-button sidebar__close" onClick={() => setMenuOpen(false)} aria-label="Close menu"><Icon name="close" /></button>
        </div>
        <nav className="nav-list" aria-label="Workspace">
          {navigation.map((item) => (
            <button className={`nav-item ${page === item.id ? "is-active" : ""}`} key={item.id} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}>
              <Icon name={item.icon} size={18} /><span>{item.label}</span>
              {item.id === "orders" && pendingOrderCount ? <b className="nav-count">{pendingOrderCount}</b> : null}
              {item.id === "inventory" && lowStockCount ? <b className="nav-alert">{lowStockCount}</b> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar__spacer" />
        <div className="sidebar-note"><span><Icon name="sparkle" size={15} /></span><p><strong>Kitchen pulse</strong><br />{statusNote}</p></div>
        <div className="account-card">
          <Avatar name={user?.full_name} size="large" />
          <span className="account-card__copy"><strong>{user?.full_name}</strong><small>{user?.role || "team member"}</small></span>
          <button className="icon-button icon-button--bare" onClick={logout} aria-label="Sign out"><Icon name="logout" size={16} /></button>
        </div>
      </aside>

      <main className="workspace__main">
        <header className="topbar">
          <button className="icon-button topbar__menu" onClick={() => setMenuOpen(true)} aria-label="Open menu" aria-expanded={menuOpen} aria-controls="workspace-navigation"><Icon name="menu" /></button>
          <div className="topbar__heading"><h1>{copy.title}</h1></div>
          <div className="topbar__actions">
            <label className="search-field"><Icon name="search" size={16} /><input ref={searchRef} value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search cakes, orders, people…" aria-label="Search bakery records" /><kbd>⌘ K</kbd></label>
            {canManage ? <button className="button button--primary topbar__cta" onClick={() => onQuickAction(page)} aria-label={copy.action}><Icon name="plus" size={16} /><span>{copy.action}</span></button> : null}
          </div>
        </header>
        <div className="workspace__content">{children}</div>
      </main>

      <nav className="mobile-nav glass-panel" aria-label="Mobile navigation">
        {navigation.map((item) => <button key={item.id} className={`mobile-nav__item ${page === item.id ? "is-active" : ""}`} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}><Icon name={item.icon} size={17} /><span>{item.short}</span></button>)}
      </nav>
    </div>
  );
}
