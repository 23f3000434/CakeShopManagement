import { useEffect, useMemo, useState } from "react";
import { Icon } from "../components/Icon";
import { CakeImage } from "../components/CakeImage";
import { Modal } from "../components/Modal";
import { EmptyState, GlassPanel, PageHeading } from "../components/Primitives";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import { canManageOperations } from "../lib/permissions";

function InventoryAdjustment({ products, initialProduct, onClose, onSave }) {
  const [productId, setProductId] = useState(initialProduct ? String(initialProduct.id) : "");
  const product = products.find((item) => String(item.id) === productId);
  const [reason, setReason] = useState("restock"); const [quantity, setQuantity] = useState(1); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState(null);
  const submit = async (event) => { event.preventDefault(); if (!product) return setError("Choose a cake to adjust."); const quantity_change = (reason === "waste" ? -1 : 1) * Math.abs(Number(quantity)); if (!quantity_change) return setError("Enter a non-zero adjustment."); setBusy(true); setError(null); try { await onSave(product, { reason, quantity_change, note: note.trim() || null }); onClose(); } catch (reasonError) { setError(reasonError.message || "Stock could not be adjusted."); } finally { setBusy(false); } };
  return <Modal title={product ? `Adjust ${product.name}` : "Adjust stock"} description={product ? `Current count: ${product.stock_quantity}. Adjustments are recorded in the stock adjustment history.` : "Choose the cake whose stock you want to change."} onClose={onClose}><form className="form-grid" onSubmit={submit}>
    <label className="form-field form-field--wide">
      <span>Cake</span>
      <select aria-label="Cake" value={productId} onChange={(event) => { setProductId(event.target.value); setError(null); }} required disabled={busy || !products.length}>
        <option value="">Choose a cake…</option>
        {products.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.sku} · {item.stock_quantity} in stock</option>)}
      </select>
      {!products.length ? <small className="field-hint">Add an active cake in Cakes &amp; products before adjusting stock.</small> : null}
    </label><label className="form-field"><span>Reason</span><select value={reason} onChange={(event) => setReason(event.target.value)}><option value="restock">Restock</option><option value="adjustment">Count correction</option><option value="waste">Waste / damage</option><option value="return">Customer return</option></select></label><label className="form-field"><span>{reason === "waste" ? "Units to remove" : "Units to add"}</span><input type="number" min="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label className="form-field form-field--wide"><span>Note <em>optional</em></span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="A short traceable note for the shift…" /></label>{error ? <div className="form-error form-field--wide"><Icon name="alert" size={15} />{error}</div> : null}<div className="form-actions form-field--wide"><button type="button" className="button button--secondary" onClick={onClose}>Cancel</button><button className="button button--primary" disabled={busy || !product}>{busy ? "Recording…" : "Record adjustment"}</button></div></form></Modal>;
}

export default function InventoryPage({ data, search, quickAction, onConsumeQuickAction }) {
  const { products, lowStock, adjustStock } = data; const [modal, setModal] = useState(null); const notify = useToast();
  const { user } = useAuth();
  const canManage = canManageOperations(user);
  useEffect(() => {
    if (quickAction?.page === "inventory") {
      if (canManage) setModal({ kind: "adjust", product: null });
      onConsumeQuickAction?.(quickAction.id);
    }
  }, [quickAction, lowStock, products, onConsumeQuickAction, canManage]);
  const visibleLowStock = useMemo(() => lowStock.filter((product) => !search || [product.name, product.sku, product.category].join(" ").toLowerCase().includes(search.toLowerCase())), [lowStock, search]);
  const stockOverview = useMemo(() => ({ active: products.filter((product) => product.is_active).length, healthy: products.filter((product) => product.is_active && product.stock_quantity > product.reorder_level).length, low: lowStock.length }), [products, lowStock]);
  const save = async (product, fields) => { await adjustStock(product, fields); notify(`${product.name}: stock count updated.`, { title: "Inventory updated" }); };
  return <div className="page page--inventory"><PageHeading description="See low-stock items and record every stock adjustment." />
    <div className="inventory-summary"><GlassPanel><span className="summary-icon summary-icon--mint"><Icon name="cake" size={18} /></span><div><span>Active cake lines</span><strong>{stockOverview.active}</strong></div></GlassPanel><GlassPanel><span className="summary-icon summary-icon--blue"><Icon name="check" size={18} /></span><div><span>Healthy stock</span><strong>{stockOverview.healthy}</strong></div></GlassPanel><GlassPanel><span className="summary-icon summary-icon--rose"><Icon name="alert" size={18} /></span><div><span>Needs attention</span><strong>{stockOverview.low}</strong></div></GlassPanel></div>
    <GlassPanel className="inventory-panel" padding={false}><header className="inventory-panel__header"><div><h2>Low-stock alerts</h2><p>Items at or below their restock threshold.</p></div><span className="stock-ledger-note"><Icon name="sparkle" size={14} /> All changes recorded</span></header>{visibleLowStock.length ? <div className="inventory-alert-list">{visibleLowStock.map((product) => { const ratio = Math.min(100, (product.stock_quantity / Math.max(1, product.reorder_level * 2)) * 100); return <article className="inventory-alert" key={product.id}><CakeImage product={product} className="inventory-alert__art" /><div className="inventory-alert__copy"><strong>{product.name}</strong><span>{product.sku} · restock threshold {product.reorder_level} units</span></div><div className="inventory-alert__level"><span><i style={{ width: `${ratio}%` }} /></span><small>{product.stock_quantity} units left</small></div>{canManage ? <button className="button button--secondary button--small" onClick={() => setModal({ kind: "adjust", product })}>Adjust</button> : null}</article>; })}</div> : <EmptyState icon="check" title="No products need restocking" description="No active cake lines are at their restock threshold." />}</GlassPanel>
    {modal?.kind === "adjust" ? <InventoryAdjustment products={products.filter((product) => product.is_active)} initialProduct={modal.product} onClose={() => setModal(null)} onSave={save} /> : null}
  </div>;
}
