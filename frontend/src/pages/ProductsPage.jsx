import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { ConfirmDialog, Modal } from "../components/Modal";
import { CakeImage } from "../components/CakeImage";
import { Icon } from "../components/Icon";
import { EmptyState, GlassPanel, PageHeading } from "../components/Primitives";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import { money } from "../lib/formatters";
import { canManageOperations } from "../lib/permissions";

const emptyProduct = {
  sku: "",
  name: "",
  category: "Signature cakes",
  description: "",
  unit_price: "",
  cost_price: "",
  stock_quantity: 10,
  reorder_level: 4,
  image_url: "",
  is_active: true
};

const categories = ["All cakes", "Signature cakes", "Chocolate", "Celebration", "Seasonal", "Vegan"];

const PHOTO_PRESETS = [
  {
    name: "Dark Chocolate Truffle",
    url: "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Red Velvet Bloom",
    url: "https://images.unsplash.com/photo-1586788680434-30d324b2d46f?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Vanilla Berry Gateau",
    url: "https://images.unsplash.com/photo-1535141192574-5d4897c13136?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Hazelnut Espresso Gateau",
    url: "https://images.unsplash.com/photo-1606890737304-57a1ca8a5b62?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Pistachio Rose Entremet",
    url: "https://images.unsplash.com/photo-1565958011703-44f9829ba187?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Salted Caramel Pecan",
    url: "https://images.unsplash.com/photo-1563729784474-d77dbb933a9e?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Lemon Blueberry Tart",
    url: "https://images.unsplash.com/photo-1519869325930-281384150729?auto=format&fit=crop&w=600&q=80"
  },
  {
    name: "Vegan Dark Fudge",
    url: "https://images.unsplash.com/photo-1542826438-bd32f43d626f?auto=format&fit=crop&w=600&q=80"
  }
];

function generateSkuSuggestion(name) {
  if (!name || !name.trim()) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  let prefix = "";
  if (parts.length === 1) {
    prefix = parts[0].slice(0, 3).toUpperCase();
  } else {
    prefix = parts.slice(0, 3).map((p) => p[0]).join("").toUpperCase();
  }
  const randNum = Math.floor(10 + Math.random() * 90);
  return `${prefix}-${randNum}`;
}

const ProductRow = memo(function ProductRow({ product, onEdit, onStock, onArchive, canManage }) {
  const isLow = product.stock_quantity <= product.reorder_level;
  return (
    <tr>
      <td>
        <div className="product-cell">
          <CakeImage product={product} className="product-art" alt={product.name} />
          <span>
            <strong>{product.name}</strong>
            <small>{product.sku} · {product.category}</small>
          </span>
        </div>
      </td>
      <td className="cell-money">{money(product.unit_price)}</td>
      <td>
        <span className={`stock-count ${isLow ? "is-low" : ""}`}>
          {product.stock_quantity} <small>in stock</small>
        </span>
      </td>
      <td>
        <span className="availability">
          <i className={product.is_active ? "is-active" : ""} />
          {product.is_active ? "Available" : "Archived"}
        </span>
      </td>
      {canManage ? (
        <td>
          <div className="row-actions">
            <button className="table-icon" onClick={() => onStock(product)} title="Adjust stock" aria-label={`Adjust ${product.name} stock`}>
              <Icon name="package" size={16} />
            </button>
            <button className="table-icon" onClick={() => onEdit(product)} title="Edit cake" aria-label={`Edit ${product.name}`}>
              <Icon name="edit" size={16} />
            </button>
            <button className="table-icon" onClick={() => onArchive(product)} title="Archive cake" aria-label={`Archive ${product.name}`}>
              <Icon name="archive" size={16} />
            </button>
          </div>
        </td>
      ) : null}
    </tr>
  );
});

const ProductCard = memo(function ProductCard({ product, onEdit, onStock, onArchive, canManage }) {
  const isLow = product.stock_quantity <= product.reorder_level;
  return (
    <div className="cake-showcase-card glass-panel">
      <div className="cake-showcase-card__photo-wrap">
        <CakeImage product={product} className="cake-showcase-card__photo" alt={product.name} />
        <span className="cake-showcase-card__price-badge">{money(product.unit_price)}</span>
        <span className={`cake-showcase-card__stock-badge ${isLow ? "is-low" : ""}`}>
          {isLow ? `Low stock (${product.stock_quantity})` : `${product.stock_quantity} in stock`}
        </span>
      </div>
      <div className="cake-showcase-card__content">
        <div className="cake-showcase-card__meta">
          <span className="cake-showcase-card__category">{product.category}</span>
          <span className="cake-showcase-card__sku">{product.sku}</span>
        </div>
        <h3 className="cake-showcase-card__title" title={product.name}>{product.name}</h3>
        {product.description && (
          <p className="cake-showcase-card__desc">{product.description}</p>
        )}
        <div className="cake-showcase-card__footer">
          <span className="availability">
            <i className={product.is_active ? "is-active" : ""} />
            {product.is_active ? "Active" : "Archived"}
          </span>
          {canManage && (
            <div className="cake-showcase-card__actions">
              <button
                type="button"
                className="button button--secondary button--small"
                onClick={() => onStock(product)}
                title="Adjust inventory"
              >
                <Icon name="package" size={13} /> Stock
              </button>
              <button
                type="button"
                className="button button--secondary button--small"
                onClick={() => onEdit(product)}
                title="Edit cake"
              >
                <Icon name="edit" size={13} /> Edit
              </button>
              <button
                type="button"
                className="table-icon"
                onClick={() => onArchive(product)}
                title="Archive cake"
              >
                <Icon name="archive" size={15} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

function ProductForm({ product, onClose, onSave }) {
  const editing = Boolean(product);
  const [form, setForm] = useState(() => product || emptyProduct);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const nameRef = useRef(null);

  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const update = (event) => {
    const { name, value, type, checked } = event.target;
    setForm((current) => {
      const next = { ...current, [name]: type === "checkbox" ? checked : value };
      // Auto-suggest SKU when user types cake name if not editing and user hasn't typed custom SKU
      if (name === "name" && !editing && (!current.sku || current.sku === generateSkuSuggestion(current.name))) {
        next.sku = generateSkuSuggestion(value);
      }
      return next;
    });
  };

  const setPhotoUrl = (url) => {
    setForm((current) => ({ ...current, image_url: url }));
  };

  const autoGenerateSku = () => {
    setForm((current) => ({ ...current, sku: generateSkuSuggestion(current.name || "Cake") }));
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setError("Cake name is required.");
      return;
    }
    if (!form.sku.trim()) {
      setError("SKU is required.");
      return;
    }
    if (form.unit_price === "" || Number(form.unit_price) < 0) {
      setError("Please enter a valid counter sale price.");
      return;
    }
    setBusy(true);
    setError(null);

    const fields = {
      sku: form.sku.trim().toUpperCase(),
      name: form.name.trim(),
      category: form.category.trim() || "Signature cakes",
      description: (form.description || "").trim() || null,
      unit_price: Number(form.unit_price),
      cost_price: form.cost_price === "" ? null : Number(form.cost_price),
      reorder_level: Math.max(0, Number(form.reorder_level) || 0),
      image_url: (form.image_url || "").trim() || null,
      is_active: Boolean(form.is_active)
    };

    if (!editing) {
      fields.stock_quantity = Math.max(0, Number(form.stock_quantity) || 0);
    }

    try {
      await onSave(fields);
      onClose();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "This cake could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={editing ? `Edit ${product.name}` : "Add New Artisan Cake"}
      description={editing ? "Update pricing, photo, description, and counter visibility." : "Add a fresh creation to your patisserie counter catalogue."}
      onClose={onClose}
      size="wide"
    >
      <form className="easy-cake-form" onSubmit={submit}>
        {/* Basic Information */}
        <div className="form-section-title">
          <Icon name="cake" size={15} />
          <span>Cake Details</span>
        </div>

        <div className="easy-form-grid">
          <label className="form-field form-field--wide">
            <span>Cake Name *</span>
            <input
              ref={nameRef}
              name="name"
              value={form.name}
              onChange={update}
              placeholder="e.g. Raspberry Dark Chocolate Truffle"
              required
            />
          </label>

          <label className="form-field">
            <span>Category</span>
            <select name="category" value={form.category} onChange={update}>
              {categories.slice(1).map((cat) => (
                <option value={cat} key={cat}>{cat}</option>
              ))}
              <option value="Pastries">Pastries</option>
              <option value="Tarts">Tarts</option>
              <option value="Cheesecakes">Cheesecakes</option>
            </select>
          </label>

          <label className="form-field">
            <span style={{ display: "flex", justifyContent: "space-between" }}>
              <span>SKU Code *</span>
              <button
                type="button"
                className="text-button"
                style={{ fontSize: "10px" }}
                onClick={autoGenerateSku}
              >
                Auto-generate
              </button>
            </span>
            <input
              name="sku"
              value={form.sku}
              onChange={update}
              placeholder="e.g. TRF-01"
              required
            />
          </label>
        </div>

        {/* Pricing & Stock */}
        <div className="form-section-title" style={{ marginTop: "10px" }}>
          <Icon name="trend" size={15} />
          <span>Pricing & Stock</span>
        </div>

        <div className="easy-form-grid">
          <label className="form-field">
            <span>Counter Sale Price (₹) *</span>
            <div className="currency-input-wrap">
              <span className="currency-prefix">₹</span>
              <input
                name="unit_price"
                type="number"
                min="0"
                step="0.01"
                value={form.unit_price}
                onChange={update}
                placeholder="1250"
                required
              />
            </div>
          </label>

          {!editing ? (
            <label className="form-field">
              <span>Opening Stock Quantity</span>
              <input
                name="stock_quantity"
                type="number"
                min="0"
                step="1"
                value={form.stock_quantity}
                onChange={update}
              />
            </label>
          ) : (
            <div className="form-field">
              <span>Current Stock</span>
              <div className="read-only-field">
                {product.stock_quantity} units
                <small> (Use stock adjustment to change)</small>
              </div>
            </div>
          )}

          <label className="form-field">
            <span>Restock Alert Level</span>
            <input
              name="reorder_level"
              type="number"
              min="0"
              step="1"
              value={form.reorder_level}
              onChange={update}
            />
          </label>

          <div className="form-field" style={{ justifyContent: "center" }}>
            <button
              type="button"
              className="text-button"
              style={{ textAlign: "left", marginTop: "18px" }}
              onClick={() => setShowAdvanced((v) => !v)}
            >
              {showAdvanced ? "− Hide cost & margin" : "+ Add cost price (for margin analysis)"}
            </button>
          </div>

          {showAdvanced && (
            <label className="form-field form-field--wide">
              <span>Kitchen Cost Price (₹) <em>optional</em></span>
              <input
                name="cost_price"
                type="number"
                min="0"
                step="0.01"
                value={form.cost_price ?? ""}
                onChange={update}
                placeholder="e.g. 480"
              />
            </label>
          )}
        </div>

        {/* Cake Photography */}
        <div className="form-section-title" style={{ marginTop: "10px" }}>
          <Icon name="camera" size={15} />
          <span>Cake Photography</span>
        </div>

        <div className="photo-selection-area">
          <div className="photo-presets-card">
            <span className="photo-presets-label">Select from popular patisserie photos (1-click):</span>
            <div className="photo-presets-list">
              {PHOTO_PRESETS.map((p) => (
                <button
                  type="button"
                  key={p.name}
                  className={`photo-preset-chip ${form.image_url === p.url ? "is-selected" : ""}`}
                  onClick={() => setPhotoUrl(p.url)}
                  title={`Use photo for ${p.name}`}
                >
                  <img src={p.url} alt={p.name} className="photo-preset-thumb" />
                  <span>{p.name}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="form-field" style={{ marginTop: "8px" }}>
            <span>Or enter custom photo URL:</span>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                name="image_url"
                type="url"
                value={form.image_url || ""}
                onChange={update}
                placeholder="https://images.unsplash.com/... or your CDN"
                style={{ flex: 1 }}
              />
              {form.image_url && (
                <button
                  type="button"
                  className="button button--secondary button--small"
                  onClick={() => setPhotoUrl("")}
                  title="Remove photo"
                >
                  Clear Photo
                </button>
              )}
            </div>
          </label>

          {/* Photo Preview Container with strict containment */}
          <div className="cake-photo-preview-box">
            <div className="cake-photo-preview-thumb">
              <CakeImage
                product={{ name: form.name || "Cake", image_url: form.image_url }}
                alt="Cake preview"
              />
            </div>
            <div className="cake-photo-preview-info">
              <strong>{form.image_url ? "Photo attached" : "No photo attached"}</strong>
              <small>
                {form.image_url
                  ? "This image is safely scaled and will be displayed in the catalogue, counter, and receipts."
                  : "Pick a preset above or paste an image link to show this cake visually at the counter."}
              </small>
            </div>
          </div>
        </div>

        {/* Description & Counter Status */}
        <label className="form-field" style={{ marginTop: "10px" }}>
          <span>Description / Flavour notes <em>optional</em></span>
          <textarea
            name="description"
            rows="2"
            value={form.description || ""}
            onChange={update}
            placeholder="A short note for counter staff: sponge type, frosting, allergens, etc."
          />
        </label>

        <label className="toggle-row" style={{ marginTop: "6px" }}>
          <span>
            <strong>Available at the counter</strong>
            <small>Show this cake in POS billing and active catalogues.</small>
          </span>
          <input
            name="is_active"
            type="checkbox"
            checked={Boolean(form.is_active)}
            onChange={update}
          />
          <i />
        </label>

        {error && (
          <div className="form-error">
            <Icon name="alert" size={15} />
            <span>{error}</span>
          </div>
        )}

        <div className="form-actions" style={{ marginTop: "14px" }}>
          <button
            type="button"
            className="button button--secondary"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button button--primary" disabled={busy}>
            {busy ? "Saving…" : editing ? "Save Changes" : "Add to Counter"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function StockModal({ product, onClose, onSave }) {
  const [reason, setReason] = useState("restock");
  const [quantity, setQuantity] = useState(1);
  const [note, setNote] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    const sign = reason === "waste" ? -1 : 1;
    const quantity_change = sign * Math.abs(Number(quantity));
    if (!quantity_change) return setError("Enter an adjustment larger than zero.");
    setBusy(true);
    setError(null);
    try {
      await onSave({ quantity_change, reason, note: note.trim() || null });
      onClose();
    } catch (reasonError) {
      setError(reasonError.message || "The stock adjustment could not be recorded.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Adjust Stock · ${product.name}`}
      description={`Currently ${product.stock_quantity} units recorded. All adjustments are logged to the inventory ledger.`}
      onClose={onClose}
    >
      <form className="form-grid" onSubmit={submit}>
        <label className="form-field">
          <span>Adjustment Reason</span>
          <select value={reason} onChange={(event) => setReason(event.target.value)}>
            <option value="restock">Restock / Fresh Bake</option>
            <option value="adjustment">Physical Count Correction</option>
            <option value="waste">Damage / Shelf Waste</option>
            <option value="return">Customer Return</option>
          </select>
        </label>
        <label className="form-field">
          <span>{reason === "waste" ? "Units to Remove" : "Units to Add"}</span>
          <input
            type="number"
            min="1"
            step="1"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </label>
        <label className="form-field form-field--wide">
          <span>Note / Shift Details <em>optional</em></span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="e.g. Morning batch from central kitchen…"
          />
        </label>
        {error && (
          <div className="form-error form-field--wide">
            <Icon name="alert" size={15} />
            {error}
          </div>
        )}
        <div className="form-actions form-field--wide">
          <button type="button" className="button button--secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button button--primary" disabled={busy}>
            {busy ? "Recording…" : "Record Adjustment"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function ProductsPage({ data, search, quickAction, onConsumeQuickAction }) {
  const { products, createProduct, updateProduct, archiveProduct, adjustStock } = data;
  const { user } = useAuth();
  const canManage = canManageOperations(user);
  const [category, setCategory] = useState("All cakes");
  const [viewMode, setViewMode] = useState("cards"); // "cards" or "table"
  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState(false);
  const notify = useToast();

  useEffect(() => {
    if (quickAction?.page === "products") {
      if (canManage) setModal({ kind: "new" });
      onConsumeQuickAction?.(quickAction.id);
    }
  }, [quickAction, onConsumeQuickAction, canManage]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return products.filter((product) => {
      const matchesCategory = category === "All cakes" || product.category === category;
      const matchesSearch = !query || [product.name, product.sku, product.category].join(" ").toLowerCase().includes(query);
      return matchesCategory && matchesSearch;
    });
  }, [products, category, search]);

  const save = useCallback(
    async (fields) => {
      if (modal?.kind === "edit") {
        await updateProduct(modal.product, fields);
        notify(`${fields.name} updated at the counter.`, { title: "Cake Updated" });
      } else {
        await createProduct(fields);
        notify(`${fields.name} added to your counter catalogue.`, { title: "Cake Added" });
      }
    },
    [modal, updateProduct, createProduct, notify]
  );

  const confirmArchive = async () => {
    setBusy(true);
    try {
      await archiveProduct(modal.product);
      notify(`${modal.product.name} is now archived.`, { title: "Cake Archived" });
      setModal(null);
    } catch (error) {
      notify(error.message, { tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const saveStock = async (fields) => {
    await adjustStock(modal.product, fields);
    notify(`Inventory updated for ${modal.product.name}.`, { title: "Stock Updated" });
  };

  return (
    <div className="page page--products">
      <div className="products-page-header">
        <PageHeading description="Manage your patisserie menu, prices, bakery photography, and counter stock." />
        <div className="products-header-controls">
          <div className="view-mode-toggle">
            <button
              type="button"
              className={`view-mode-btn ${viewMode === "cards" ? "is-active" : ""}`}
              onClick={() => setViewMode("cards")}
              title="Showcase Cards View"
            >
              <Icon name="grid" size={14} /> Cards
            </button>
            <button
              type="button"
              className={`view-mode-btn ${viewMode === "table" ? "is-active" : ""}`}
              onClick={() => setViewMode("table")}
              title="Table View"
            >
              <Icon name="list" size={14} /> Table
            </button>
          </div>
          {canManage && (
            <button className="button button--primary" onClick={() => setModal({ kind: "new" })}>
              <Icon name="plus" size={15} /> Add a Cake
            </button>
          )}
        </div>
      </div>

      <div className="filter-bar" aria-label="Cake category filters">
        {categories.map((item) => (
          <button
            className={`filter-chip ${category === item ? "is-active" : ""}`}
            onClick={() => setCategory(item)}
            key={item}
          >
            {item}
          </button>
        ))}
        <span className="result-count">{filtered.length} cakes</span>
      </div>

      {filtered.length ? (
        viewMode === "cards" ? (
          <div className="cakes-showcase-grid">
            {filtered.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                onEdit={(item) => setModal({ kind: "edit", product: item })}
                onStock={(item) => setModal({ kind: "stock", product: item })}
                onArchive={(item) => setModal({ kind: "archive", product: item })}
                canManage={canManage}
              />
            ))}
          </div>
        ) : (
          <GlassPanel className="data-panel" padding={false}>
            <div className="data-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Cake</th>
                    <th>Counter Price</th>
                    <th>Stock</th>
                    <th>Status</th>
                    {canManage ? <th aria-label="Actions" /> : null}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((product) => (
                    <ProductRow
                      key={product.id}
                      product={product}
                      onEdit={(item) => setModal({ kind: "edit", product: item })}
                      onStock={(item) => setModal({ kind: "stock", product: item })}
                      onArchive={(item) => setModal({ kind: "archive", product: item })}
                      canManage={canManage}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </GlassPanel>
        )
      ) : (
        <GlassPanel className="data-panel" padding={false}>
          <EmptyState
            icon="cake"
            title="No cakes match this view"
            description={canManage ? "Try another category or add a new cake to the catalogue." : "Try another category or clear the search to find a cake."}
            action={canManage ? (
              <button className="button button--primary" onClick={() => setModal({ kind: "new" })}>
                Add a cake
              </button>
            ) : null}
          />
        </GlassPanel>
      )}

      {modal?.kind === "new" || modal?.kind === "edit" ? (
        <ProductForm
          product={modal.kind === "edit" ? modal.product : null}
          onClose={() => setModal(null)}
          onSave={save}
        />
      ) : null}
      {modal?.kind === "stock" ? (
        <StockModal
          product={modal.product}
          onClose={() => setModal(null)}
          onSave={saveStock}
        />
      ) : null}
      {modal?.kind === "archive" ? (
        <ConfirmDialog
          title={`Archive ${modal.product.name}?`}
          description="It will disappear from the active counter catalogue, while every past order stays intact."
          confirmLabel="Archive cake"
          onClose={() => setModal(null)}
          onConfirm={confirmArchive}
          busy={busy}
        />
      ) : null}
    </div>
  );
}
