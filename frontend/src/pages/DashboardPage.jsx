import { useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { CakeImage } from "../components/CakeImage";
import { GlassPanel, MetricCard, LoadingPanel, StatusPill } from "../components/Primitives";
import { dateTime, money, shortMoney } from "../lib/formatters";

const categoryTones = ["rose", "butter", "mint"];

export default function DashboardPage({ data, onNavigate }) {
  const { dashboard, products, orders, lowStock, status, reload } = data;
  const [isRefreshing, setIsRefreshing] = useState(false);

  const metrics = dashboard?.metrics || {};

  // Compute live operational numbers directly from active state
  // so any created, edited, or status-updated order replicates immediately
  const livePendingOrders = useMemo(() => {
    return orders.filter((order) => ["confirmed", "in_progress", "ready"].includes(order.status)).length;
  }, [orders]);

  const liveLowStockCount = useMemo(() => {
    return products.filter((product) => product.is_active && product.stock_quantity <= product.reorder_level).length;
  }, [products]);

  const liveActiveProducts = useMemo(() => {
    return products.filter((product) => product.is_active).length;
  }, [products]);

  // Today's total booked sales (value of non-cancelled orders created today)
  const todayStart = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  const todayBooked = useMemo(() => {
    return orders
      .filter((o) => o.status !== "cancelled" && new Date(o.created_at) >= todayStart)
      .reduce((sum, o) => sum + Number(o.total_amount || 0), 0);
  }, [orders, todayStart]);

  const todayRevenue = Number(metrics.today_revenue || 0);

  // Derive queue and recent orders directly from live orders array
  // This guarantees instant replication on the dashboard as soon as an order is placed
  const queue = useMemo(() => {
    return orders
      .filter((order) => ["confirmed", "in_progress", "ready"].includes(order.status))
      .sort((a, b) => {
        const timeA = a.pickup_at ? new Date(a.pickup_at).getTime() : new Date(a.created_at).getTime();
        const timeB = b.pickup_at ? new Date(b.pickup_at).getTime() : new Date(b.created_at).getTime();
        return timeA - timeB;
      });
  }, [orders]);

  const recent = useMemo(() => {
    return [...orders].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [orders]);

  const dailySales = useMemo(() => (Array.isArray(dashboard?.daily_sales) ? dashboard.daily_sales : []).map((entry) => ({
    date: entry.date,
    label: entry.label || entry.date,
    netRevenue: Number.isFinite(Number(entry.net_revenue)) ? Number(entry.net_revenue) : 0
  })), [dashboard?.daily_sales]);

  const weeklyNetRevenue = useMemo(
    () => dailySales.reduce((sum, entry) => sum + entry.netRevenue, 0),
    [dailySales]
  );

  const largestDailyMagnitude = useMemo(
    () => Math.max(...dailySales.map((entry) => Math.abs(entry.netRevenue)), 0),
    [dailySales]
  );

  const hasLedgerActivity = dailySales.some((entry) => entry.netRevenue !== 0);

  const topCategories = useMemo(() => {
    const categoriesMap = products.reduce((accumulator, product) => {
      if (!product.is_active) return accumulator;
      accumulator[product.category] = (accumulator[product.category] || 0) + 1;
      return accumulator;
    }, {});
    const values = Object.entries(categoriesMap).sort((a, b) => b[1] - a[1]);
    const total = values.reduce((sum, [, count]) => sum + count, 0) || 1;
    return values.slice(0, 3).map(([label, count], index) => ({
      label,
      count,
      percentage: Math.round((count / total) * 100),
      tone: categoryTones[index % categoryTones.length]
    }));
  }, [products]);

  const categoryDonut = useMemo(() => {
    if (!topCategories.length) return undefined;
    let progress = 0;
    const segments = topCategories.map((category) => {
      const start = progress;
      progress += category.percentage;
      return `var(--${category.tone}) ${start}% ${progress}%`;
    });
    if (progress < 100) segments.push(`var(--line-soft) ${progress}% 100%`);
    return { background: `conic-gradient(${segments.join(", ")})` };
  }, [topCategories]);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      await reload();
    } finally {
      setIsRefreshing(false);
    }
  };

  if (status === "loading" && !dashboard) return <LoadingPanel />;

  return (
    <div className="dashboard">
      <div className="dashboard__hero">
        <div>
          <h2>Today’s bakery, in one place.</h2>
          <p>Real-time payment activity, live kitchen handoffs, and counter inventory updated continuously.</p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button
            className="button button--secondary"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            title="Refresh dashboard records"
          >
            <Icon name="refresh" size={14} className={isRefreshing ? "spin-icon" : ""} />
            {isRefreshing ? "Refreshing…" : "Sync"}
          </button>
          <button className="button button--primary" onClick={() => onNavigate("orders")}>
            Open POS & Orders <Icon name="arrowRight" size={15} />
          </button>
        </div>
      </div>

      <section className="metric-grid">
        <MetricCard
          label="Today’s net collections"
          value={shortMoney(todayRevenue)}
          caption="Captured counter payments less refunds today"
          tone="rose"
          icon="trend"
        />
        <MetricCard
          label="Today’s booked orders"
          value={money(todayBooked)}
          caption="Total value of active orders placed today"
          tone="butter"
          icon="receipt"
        />
        <MetricCard
          label="Orders in motion"
          value={livePendingOrders}
          caption="Confirmed, baking in kitchen, or ready"
          tone="mint"
          icon="clock"
        />
        <MetricCard
          label="Low stock alerts"
          value={liveLowStockCount}
          caption={liveLowStockCount ? `${liveLowStockCount} active cakes at or below reorder level` : "Pantry fully stocked"}
          tone="rose"
          icon="package"
        />
        <MetricCard
          label="Active catalogue"
          value={liveActiveProducts}
          caption="Artisan cakes available for counter sale"
          tone="blue"
          icon="cake"
        />
      </section>

      <section className="dashboard-grid">
        <GlassPanel className="sales-panel">
          <header className="panel-header">
            <div>
              <h2>Payment activity</h2>
              <p>Net captures less refunds, last seven business days</p>
            </div>
            <button className="text-button" onClick={() => onNavigate("orders")}>
              See all orders <Icon name="arrowRight" size={14} />
            </button>
          </header>
          <div className="sales-panel__content">
            <div className="sales-panel__chart">
              <div className="sales-panel__total">
                <strong>{money(weeklyNetRevenue)}</strong>
                <span>Seven-day net</span>
              </div>
              {dailySales.length && hasLedgerActivity ? (
                <div className="bar-chart">
                  {dailySales.map((entry, index) => {
                    const height = largestDailyMagnitude ? Math.max(8, Math.round((Math.abs(entry.netRevenue) / largestDailyMagnitude) * 100)) : 0;
                    return (
                      <div className={`bar-chart__column ${index === dailySales.length - 1 ? "is-emphasis" : ""}`} key={entry.date}>
                        <span
                          role="img"
                          aria-label={`${entry.label}: ${money(entry.netRevenue)} net payment activity`}
                          title={`${entry.label}: ${money(entry.netRevenue)} net payment activity`}
                          style={{ height: entry.netRevenue ? `${height}%` : "0%", minHeight: entry.netRevenue ? undefined : 0, opacity: entry.netRevenue < 0 ? 0.52 : 1 }}
                        />
                        <small>{entry.label}</small>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="quiet-copy">{dailySales.length ? "No captured payments or refunds were recorded in the last seven days." : "Seven-day payment history is not available yet."}</p>
              )}
            </div>
            <div className="category-card">
              <div className="category-card__donut" style={categoryDonut}>
                <div>
                  <strong>{liveActiveProducts}</strong>
                  <small>active</small>
                </div>
              </div>
              <div className="category-card__legend">
                {topCategories.length ? (
                  topCategories.map((category) => (
                    <div key={category.label}>
                      <span className={`legend-dot legend-dot--${category.tone}`} />
                      {category.label}
                      <b>{category.percentage}%</b>
                    </div>
                  ))
                ) : (
                  <span>No active products yet</span>
                )}
              </div>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel className="queue-panel">
          <header className="panel-header">
            <div>
              <h2>Kitchen queue ({queue.length})</h2>
              <p>Orders waiting for the next production step</p>
            </div>
            <button className="icon-button icon-button--bare" onClick={() => onNavigate("orders")} aria-label="Open orders">
              <Icon name="arrowRight" size={16} />
            </button>
          </header>
          <div className="queue-list">
            {queue.slice(0, 5).map((order) => (
              <article className="queue-item" key={order.id}>
                <span className="queue-item__time">
                  <Icon name="clock" size={13} />
                  {dateTime(order.pickup_at || order.created_at).replace(/^[A-Za-z]+,?\s*/, "")}
                </span>
                <div className="queue-item__copy">
                  <strong>{order.customer?.full_name || "Walk-in customer"}</strong>
                  <span>{order.order_number} · {order.fulfillment_type}</span>
                </div>
                <StatusPill status={order.status} />
              </article>
            ))}
            {!queue.length ? <p className="quiet-copy">Your production queue is clear.</p> : null}
          </div>
        </GlassPanel>

        <GlassPanel className="recent-panel">
          <header className="panel-header">
            <div>
              <h2>Recent orders</h2>
              <p>Most recently placed counter orders</p>
            </div>
            <button className="text-button" onClick={() => onNavigate("orders")}>
              All orders <Icon name="arrowRight" size={14} />
            </button>
          </header>
          <div className="recent-orders">
            {recent.slice(0, 5).map((order) => (
              <article className="recent-order" key={order.id}>
                <span className="recent-order__avatar">
                  {(order.customer?.full_name || "W").slice(0, 1)}
                </span>
                <div className="recent-order__copy">
                  <strong>{order.customer?.full_name || "Walk-in order"}</strong>
                  <small>{order.order_number} · {dateTime(order.created_at)}</small>
                </div>
                <span className="recent-order__money">{money(order.total_amount)}</span>
                <StatusPill status={order.status} />
              </article>
            ))}
            {!recent.length ? <p className="quiet-copy">New orders will appear here as soon as they’re created.</p> : null}
          </div>
        </GlassPanel>

        <GlassPanel className="stock-panel">
          <header className="panel-header">
            <div>
              <h2>Stock to watch</h2>
              <p>Products at or below their restock level</p>
            </div>
            <button className="text-button" onClick={() => onNavigate("inventory")}>
              Inventory <Icon name="arrowRight" size={14} />
            </button>
          </header>
          <div className="stock-watch-list">
            {products
              .filter((p) => p.is_active && p.stock_quantity <= p.reorder_level)
              .slice(0, 5)
              .map((product) => (
                <article className="stock-watch" key={product.id}>
                  <CakeImage product={product} className="stock-watch__emoji" alt={product.name} />
                  <div>
                    <strong>{product.name}</strong>
                    <span>{product.stock_quantity} left · restock at {product.reorder_level}</span>
                  </div>
                  <span className="stock-watch__bar">
                    <i
                      style={{
                        width: `${Math.min(100, (product.stock_quantity / Math.max(product.reorder_level * 2, 1)) * 100)}%`
                      }}
                    />
                  </span>
                </article>
              ))}
            {!products.some((p) => p.is_active && p.stock_quantity <= p.reorder_level) ? (
              <p className="quiet-copy">No low-stock items right now. Your pantry is set.</p>
            ) : null}
          </div>
        </GlassPanel>
      </section>
    </div>
  );
}
