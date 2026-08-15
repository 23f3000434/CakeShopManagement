import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { CakeImage } from "../components/CakeImage";
import { Icon } from "../components/Icon";
import { ConfirmDialog, Modal } from "../components/Modal";
import { EmptyState, GlassPanel, PageHeading, StatusPill } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { allowedTransitions, dateTime, money } from "../lib/formatters";
import { canManageOperations } from "../lib/permissions";

const ORDER_TABS = [
  { id: "all", label: "All orders" },
  { id: "draft", label: "Drafts" },
  { id: "confirmed", label: "Confirmed" },
  { id: "in_progress", label: "In Kitchen" },
  { id: "ready", label: "Ready for Pickup" },
  { id: "completed", label: "Completed" },
  { id: "cancelled", label: "Cancelled" }
];

const PAYMENT_METHODS = [
  { id: "cash", label: "Cash" },
  { id: "upi", label: "UPI" },
  { id: "card", label: "Credit / Debit Card" },
  { id: "bank_transfer", label: "Bank Transfer" }
];

/* -------------------------------------------------------------------------- */
/* Cake Card in Visual Billing Picker                                         */
/* -------------------------------------------------------------------------- */
const CakePickerCard = memo(function CakePickerCard({ product, inCartQty, onAdd }) {
  const isOutOfStock = product.stock_quantity <= 0;
  return (
    <div className={`cake-picker-card ${isOutOfStock ? "is-out-of-stock" : ""}`} onClick={() => !isOutOfStock && onAdd(product)}>
      <div className="cake-picker-card__photo-wrap">
        <CakeImage product={product} className="cake-picker-card__photo" alt={product.name} />
        {inCartQty > 0 ? (
          <span className="cake-picker-card__in-cart-badge">{inCartQty} in cart</span>
        ) : null}
      </div>
      <div className="cake-picker-card__info">
        <div className="cake-picker-card__header">
          <strong className="cake-picker-card__name">{product.name}</strong>
          <span className="cake-picker-card__sku">{product.sku}</span>
        </div>
        <div className="cake-picker-card__meta">
          <span className="cake-picker-card__price">{money(product.unit_price)}</span>
          <span className={`cake-picker-card__stock ${product.is_low_stock ? "is-low" : ""}`}>
            {isOutOfStock ? "Sold out" : `${product.stock_quantity} left`}
          </span>
        </div>
      </div>
      <button
        type="button"
        className="button button--secondary button--small cake-picker-card__add-btn"
        disabled={isOutOfStock}
        onClick={(e) => {
          e.stopPropagation();
          onAdd(product);
        }}
        title={`Add ${product.name} to bill`}
      >
        <Icon name="plus" size={13} /> Add to bill
      </button>
    </div>
  );
});

/* -------------------------------------------------------------------------- */
/* Line Item in Order Cart                                                    */
/* -------------------------------------------------------------------------- */
const CartLineItem = memo(function CartLineItem({ item, onQuantityChange, onRemove }) {
  return (
    <div className="billing-cart-item">
      <CakeImage product={item.product} className="billing-cart-item__photo" alt={item.product.name} />
      <div className="billing-cart-item__details">
        <strong>{item.product.name}</strong>
        <small>{money(item.product.unit_price)} each</small>
      </div>
      <div className="billing-cart-item__stepper">
        <button
          type="button"
          className="stepper-btn"
          onClick={() => onQuantityChange(item.product.id, item.quantity - 1)}
          aria-label="Decrease quantity"
        >
          -
        </button>
        <input
          type="number"
          min="1"
          max={item.product.stock_quantity || 999}
          value={item.quantity}
          onChange={(e) => onQuantityChange(item.product.id, Math.max(1, parseInt(e.target.value, 10) || 1))}
          className="stepper-input"
          aria-label={`Quantity for ${item.product.name}`}
        />
        <button
          type="button"
          className="stepper-btn"
          onClick={() => onQuantityChange(item.product.id, item.quantity + 1)}
          aria-label="Increase quantity"
        >
          +
        </button>
      </div>
      <span className="billing-cart-item__total">{money(item.product.unit_price * item.quantity)}</span>
      <button
        type="button"
        className="table-icon billing-cart-item__remove"
        onClick={() => onRemove(item.product.id)}
        aria-label="Remove item"
      >
        <Icon name="close" size={14} />
      </button>
    </div>
  );
});

/* -------------------------------------------------------------------------- */
/* POS Billing & New Order Modal                                              */
/* -------------------------------------------------------------------------- */
function OrderBillingModal({ products, customers, onClose, onSave, onQuickCustomerCreate }) {
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [cakeSearch, setCakeSearch] = useState("");
  const [cart, setCart] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [showQuickCustomer, setShowQuickCustomer] = useState(false);
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [fulfillmentType, setFulfillmentType] = useState("pickup");
  const [pickupAt, setPickupAt] = useState("");
  const [deliveryAddress, setDeliveryAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [discountAmount, setDiscountAmount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [posTab, setPosTab] = useState("catalogue"); // "catalogue" | "bill" for smaller screens

  const categories = useMemo(() => {
    const list = ["All"];
    products.forEach((p) => {
      if (p.category && !list.includes(p.category)) list.push(p.category);
    });
    return list;
  }, [products]);

  const filteredProducts = useMemo(() => {
    const needle = cakeSearch.trim().toLowerCase();
    return products.filter((p) => {
      if (!p.is_active) return false;
      const matchesCategory = selectedCategory === "All" || p.category === selectedCategory;
      const matchesSearch = !needle || [p.name, p.sku, p.category].join(" ").toLowerCase().includes(needle);
      return matchesCategory && matchesSearch;
    });
  }, [products, selectedCategory, cakeSearch]);

  const addToCart = useCallback((product) => {
    setCart((prev) => {
      const existing = prev.find((i) => i.product.id === product.id);
      if (existing) {
        return prev.map((i) => (i.product.id === product.id ? { ...i, quantity: i.quantity + 1 } : i));
      }
      return [...prev, { product, quantity: 1 }];
    });
  }, []);

  const changeQuantity = useCallback((productId, qty) => {
    if (qty <= 0) {
      setCart((prev) => prev.filter((i) => i.product.id !== productId));
      return;
    }
    setCart((prev) => prev.map((i) => (i.product.id === productId ? { ...i, quantity: qty } : i)));
  }, []);

  const removeFromCart = useCallback((productId) => {
    setCart((prev) => prev.filter((i) => i.product.id !== productId));
  }, []);

  const subtotal = useMemo(() => {
    return cart.reduce((sum, i) => sum + i.product.unit_price * i.quantity, 0);
  }, [cart]);

  const grandTotal = useMemo(() => {
    return Math.max(0, subtotal - Number(discountAmount || 0));
  }, [subtotal, discountAmount]);

  const handleQuickCustomer = async () => {
    if (!newCustomerName.trim()) return;
    try {
      const created = await onQuickCustomerCreate({
        full_name: newCustomerName.trim(),
        phone: newCustomerPhone.trim() || null
      });
      setCustomerId(created.id);
      setShowQuickCustomer(false);
      setNewCustomerName("");
      setNewCustomerPhone("");
    } catch (err) {
      setError(err.message || "Could not create customer.");
    }
  };

  const handleCheckout = async (confirmImmediately = false) => {
    if (cart.length === 0) {
      setError("Add at least one cake to the bill.");
      return;
    }
    if (fulfillmentType === "delivery" && !deliveryAddress.trim()) {
      setError("Please provide a delivery address.");
      return;
    }
    setBusy(true);
    setError(null);

    const items = cart.map((i) => ({
      product_id: i.product.id,
      quantity: i.quantity
    }));

    const orderPayload = {
      customer_id: customerId ? Number(customerId) : null,
      fulfillment_type: fulfillmentType,
      pickup_at: pickupAt ? new Date(pickupAt).toISOString() : null,
      delivery_address: fulfillmentType === "delivery" ? deliveryAddress.trim() : null,
      notes: notes.trim() || null,
      discount_amount: Number(discountAmount || 0),
      items
    };

    try {
      await onSave(orderPayload, confirmImmediately);
      onClose();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The order could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Point of Sale — Cake Billing"
      description="Select cakes from the visual catalogue, build the bill, and send directly to kitchen."
      onClose={onClose}
      size="pos"
    >
      <div className="pos-mobile-nav">
        <button
          type="button"
          className={`pos-mobile-nav__btn ${posTab === "catalogue" ? "is-active" : ""}`}
          onClick={() => setPosTab("catalogue")}
        >
          <Icon name="cake" size={14} /> Menu ({filteredProducts.length})
        </button>
        <button
          type="button"
          className={`pos-mobile-nav__btn ${posTab === "bill" ? "is-active" : ""}`}
          onClick={() => setPosTab("bill")}
        >
          <Icon name="receipt" size={14} /> Bill ({cart.reduce((s, i) => s + i.quantity, 0)} items · {money(grandTotal)})
        </button>
      </div>

      <div className="billing-pos-container">
        {/* Left Side: Cake Visual Catalogue Picker */}
        <div className={`billing-pos-catalogue ${posTab === "bill" ? "is-mobile-hidden" : ""}`}>
          <div className="catalogue-filters">
            <div className="catalogue-categories-bar">
              {categories.map((cat) => (
                <button
                  type="button"
                  key={cat}
                  className={`filter-chip ${selectedCategory === cat ? "is-active" : ""}`}
                  onClick={() => setSelectedCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
            <div className="search-field catalogue-search">
              <Icon name="search" size={15} />
              <input
                type="text"
                placeholder="Search cake name, SKU..."
                value={cakeSearch}
                onChange={(e) => setCakeSearch(e.target.value)}
              />
            </div>
          </div>

          <div className="cake-picker-grid">
            {filteredProducts.map((p) => {
              const inCart = cart.find((i) => i.product.id === p.id);
              return (
                <CakePickerCard
                  key={p.id}
                  product={p}
                  inCartQty={inCart ? inCart.quantity : 0}
                  onAdd={addToCart}
                />
              );
            })}
            {!filteredProducts.length && (
              <p className="quiet-copy" style={{ gridColumn: "1 / -1", padding: "40px 0" }}>
                No cakes match the current category or search.
              </p>
            )}
          </div>
        </div>

        {/* Right Side: Billing Cart Sheet */}
        <div className={`billing-pos-sheet glass-panel ${posTab === "catalogue" ? "is-mobile-hidden" : ""}`}>
          <div className="billing-sheet-header">
            <h3>Bill & Order Details</h3>
            <span className="billing-item-count">{cart.reduce((s, i) => s + i.quantity, 0)} items</span>
          </div>

          <div className="billing-sheet-body">
            {/* Customer Selection */}
            <div className="billing-section">
              <div className="billing-section-title">
                <span>Customer</span>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setShowQuickCustomer((v) => !v)}
                >
                  {showQuickCustomer ? "Select existing" : "+ New customer"}
                </button>
              </div>
              {showQuickCustomer ? (
                <div className="quick-customer-form">
                  <input
                    type="text"
                    placeholder="Customer name"
                    value={newCustomerName}
                    onChange={(e) => setNewCustomerName(e.target.value)}
                    className="quick-input"
                  />
                  <input
                    type="text"
                    placeholder="Phone number"
                    value={newCustomerPhone}
                    onChange={(e) => setNewCustomerPhone(e.target.value)}
                    className="quick-input"
                  />
                  <button
                    type="button"
                    className="button button--secondary button--small"
                    onClick={handleQuickCustomer}
                  >
                    Save & Bind
                  </button>
                </div>
              ) : (
                <select
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                  className="billing-select"
                  aria-label="Customer"
                >
                  <option value="">Walk-in Customer</option>
                  {customers.filter((c) => c.is_active).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.full_name} {c.phone ? `(${c.phone})` : ""}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Fulfillment Toggle */}
            <div className="billing-section">
              <span className="billing-section-label">Fulfillment Mode</span>
              <div className="fulfillment-toggle-group">
                <button
                  type="button"
                  className={`toggle-btn ${fulfillmentType === "pickup" ? "is-active" : ""}`}
                  onClick={() => setFulfillmentType("pickup")}
                >
                  Store Pickup
                </button>
                <button
                  type="button"
                  className={`toggle-btn ${fulfillmentType === "delivery" ? "is-active" : ""}`}
                  onClick={() => setFulfillmentType("delivery")}
                >
                  Home Delivery
                </button>
              </div>
              {fulfillmentType === "pickup" ? (
                <label className="form-field form-field--compact" style={{ marginTop: "8px" }}>
                  <span>Scheduled Pickup Date & Time</span>
                  <input
                    type="datetime-local"
                    value={pickupAt}
                    onChange={(e) => setPickupAt(e.target.value)}
                  />
                </label>
              ) : (
                <label className="form-field form-field--compact" style={{ marginTop: "8px" }}>
                  <span>Delivery Address</span>
                  <textarea
                    rows="2"
                    placeholder="Street address, landmark, PIN code"
                    value={deliveryAddress}
                    onChange={(e) => setDeliveryAddress(e.target.value)}
                  />
                </label>
              )}
            </div>

            {/* Cart Items List */}
            <div className="billing-cart-items-wrap">
              <span className="billing-section-label">Selected Cakes</span>
              <div className="billing-cart-list">
                {cart.map((item) => (
                  <CartLineItem
                    key={item.product.id}
                    item={item}
                    onQuantityChange={changeQuantity}
                    onRemove={removeFromCart}
                  />
                ))}
                {!cart.length && (
                  <div className="empty-cart-hint">
                    <Icon name="cake" size={24} />
                    <p>Click cakes on the left to add them to this bill.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Custom Cake Message / Notes */}
            <div className="billing-section">
              <label className="form-field form-field--compact">
                <span>Cake Dedication / Kitchen Instructions</span>
                <input
                  type="text"
                  placeholder="e.g. 'Happy 25th Rhea!', eggless, extra garnish"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
            </div>
          </div>

          {/* Sticky Footer: Totals and Actions */}
          <div className="billing-sheet-footer">
            <div className="billing-totals-card">
              <div className="billing-totals-row">
                <span>Subtotal</span>
                <b>{money(subtotal)}</b>
              </div>
              <div className="billing-totals-row">
                <span>Discount (₹)</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={discountAmount}
                  onChange={(e) => setDiscountAmount(Math.max(0, parseFloat(e.target.value) || 0))}
                  className="discount-input"
                  aria-label="Discount (₹)"
                />
              </div>
              <div className="billing-totals-row billing-grand-total">
                <strong>Grand Total</strong>
                <em>{money(grandTotal)}</em>
              </div>
            </div>

            {error && (
              <div className="form-error">
                <Icon name="alert" size={14} />
                <span>{error}</span>
              </div>
            )}

            <div className="billing-action-buttons">
              <button
                type="button"
                className="button button--secondary"
                onClick={() => handleCheckout(false)}
                disabled={busy || !cart.length}
              >
                Save as Draft
              </button>
              <button
                type="button"
                className="button button--primary"
                onClick={() => handleCheckout(true)}
                disabled={busy || !cart.length}
              >
                {busy ? "Processing…" : "Confirm & Place Order"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Printable Bill / Invoice Receipt Modal                                     */
/* -------------------------------------------------------------------------- */
function OrderReceiptModal({ order, onClose, onRecordPayment }) {
  const handlePrint = () => {
    document.body.classList.add("is-printing-receipt");
    window.print();
    const cleanup = () => {
      document.body.classList.remove("is-printing-receipt");
      window.removeEventListener("afterprint", cleanup);
    };
    window.addEventListener("afterprint", cleanup, { once: true });
    setTimeout(cleanup, 3000);
  };

  const capturedTotal = useMemo(() => {
    return (order.payments || [])
      .filter((p) => p.status === "captured")
      .reduce((sum, p) => sum + Number(p.amount || 0), 0);
  }, [order.payments]);

  const refundedTotal = useMemo(() => {
    return (order.payments || [])
      .filter((p) => p.status === "refunded")
      .reduce((sum, p) => sum + Number(p.amount || 0), 0);
  }, [order.payments]);

  const netPaid = capturedTotal - refundedTotal;
  const balanceDue = Math.max(0, Number(order.total_amount || 0) - netPaid);

  return (
    <Modal title={`Receipt #${order.order_number}`} description="Store receipt, customer bill, and payment verification." onClose={onClose} size="wide">
      <div className="receipt-container" id="printable-receipt">
        {/* Receipt Header */}
        <div className="receipt-header">
          <div className="receipt-brand">
            <span className="brand__mark">B</span>
            <div>
              <h2>Butterlane Cake Atelier</h2>
              <p>Specialty Bakery & Patisserie · Tax Invoice / Bill</p>
            </div>
          </div>
          <div className="receipt-meta">
            <div><strong>Order #:</strong> <span>{order.order_number}</span></div>
            <div><strong>Date:</strong> <span>{dateTime(order.created_at)}</span></div>
            <div><strong>Fulfillment:</strong> <span style={{ textTransform: "capitalize" }}>{order.fulfillment_type}</span></div>
            {order.pickup_at && <div><strong>Scheduled:</strong> <span>{dateTime(order.pickup_at)}</span></div>}
          </div>
        </div>

        {/* Customer & Fulfillment Info */}
        <div className="receipt-customer-bar">
          <div>
            <small>Customer</small>
            <strong>{order.customer?.full_name || "Walk-in Guest"}</strong>
            {order.customer?.phone && <span>{order.customer.phone}</span>}
          </div>
          {order.delivery_address && (
            <div>
              <small>Delivery Address</small>
              <p>{order.delivery_address}</p>
            </div>
          )}
          {order.notes && (
            <div>
              <small>Cake Message / Instructions</small>
              <p>{order.notes}</p>
            </div>
          )}
        </div>

        {/* Itemized Table with Cake Photography */}
        <table className="receipt-items-table">
          <thead>
            <tr>
              <th style={{ width: "48px" }}>Photo</th>
              <th>Item Description</th>
              <th style={{ textAlign: "right" }}>Price</th>
              <th style={{ textAlign: "center" }}>Qty</th>
              <th style={{ textAlign: "right" }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {(order.items || []).map((item) => (
              <tr key={item.id}>
                <td>
                  <CakeImage
                    product={{ name: item.product_name, image_url: item.image_url }}
                    className="receipt-item-photo"
                    alt={item.product_name}
                  />
                </td>
                <td>
                  <strong>{item.product_name}</strong>
                </td>
                <td style={{ textAlign: "right" }}>{money(item.unit_price)}</td>
                <td style={{ textAlign: "center" }}>{item.quantity}</td>
                <td style={{ textAlign: "right" }}><strong>{money(item.line_total)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Summary Totals */}
        <div className="receipt-summary-grid">
          <div className="receipt-payments-history">
            <h4>Payment Records</h4>
            {(order.payments && order.payments.length > 0) ? (
              <ul className="receipt-payments-list">
                {order.payments.map((p) => (
                  <li key={p.id}>
                    <span>{p.method.toUpperCase()} ({p.status}) · {dateTime(p.created_at)}</span>
                    <b>{p.status === "refunded" ? `-${money(p.amount)}` : money(p.amount)}</b>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="quiet-copy" style={{ textAlign: "left", margin: "6px 0" }}>No payments recorded yet.</p>
            )}
          </div>

          <div className="receipt-totals-table">
            <div className="receipt-totals-row">
              <span>Item Subtotal</span>
              <b>{money(order.subtotal)}</b>
            </div>
            {Number(order.discount_amount) > 0 && (
              <div className="receipt-totals-row">
                <span>Discount Applied</span>
                <b style={{ color: "var(--danger)" }}>-{money(order.discount_amount)}</b>
              </div>
            )}
            {Number(order.tax_amount) > 0 && (
              <div className="receipt-totals-row">
                <span>Tax ({order.tax_rate}%)</span>
                <b>{money(order.tax_amount)}</b>
              </div>
            )}
            <div className="receipt-totals-row receipt-totals-grand">
              <strong>Total Bill Amount</strong>
              <em>{money(order.total_amount)}</em>
            </div>
            <div className="receipt-totals-row">
              <span>Total Paid</span>
              <b style={{ color: "var(--mint)" }}>{money(netPaid)}</b>
            </div>
            <div className="receipt-totals-row receipt-balance-due">
              <span>Balance Remaining</span>
              <b>{money(balanceDue)}</b>
            </div>
          </div>
        </div>

        {/* Printable store footer */}
        <div className="receipt-print-footer">
          <p className="receipt-print-footer__thanks">Thank you for ordering with Butterlane Cake Atelier!</p>
          <p>Handcrafted artisan cakes & patisserie · For custom celebrations, email orders@butterlane.local</p>
          <p className="receipt-print-footer__audit">Generated on {dateTime(new Date())} · Official Store Tax Invoice</p>
        </div>

        {/* Actions */}
        <div className="receipt-modal-actions no-print">
          <button type="button" className="button button--secondary" onClick={handlePrint}>
            <Icon name="printer" size={15} /> Print Bill Receipt
          </button>
          {balanceDue > 0 && (
            <button
              type="button"
              className="button button--primary"
              onClick={() => onRecordPayment(order, balanceDue)}
            >
              <Icon name="card" size={15} /> Record Payment ({money(balanceDue)})
            </button>
          )}
          <button type="button" className="button button--secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Payment Modal                                                              */
/* -------------------------------------------------------------------------- */
function PaymentCaptureModal({ order, initialAmount, onClose, onSave }) {
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState(initialAmount || order.total_amount);
  const [refCode, setRefCode] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    const num = parseFloat(amount);
    if (!num || num <= 0) {
      setError("Please enter a payment amount greater than zero.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave({
        method,
        amount: num,
        provider_reference: refCode.trim() || null,
        note: note.trim() || null
      });
      onClose();
    } catch (err) {
      setError(err.message || "Payment could not be recorded.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`Record Payment · ${order.order_number}`} description="Capture cash, card, UPI, or bank transfer for this order." onClose={onClose}>
      <form className="form-grid" onSubmit={submit}>
        <div className="form-field form-field--wide" style={{ padding: "10px 12px", borderRadius: "12px", background: "rgba(255,254,249,.6)", border: "1px solid rgba(255,252,244,.8)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#553a28" }}>
            <span>Order Total: <b>{money(order.total_amount)}</b></span>
            <span>Remaining Balance: <b style={{ color: "var(--rose-deep)" }}>{money(initialAmount || order.total_amount)}</b></span>
          </div>
        </div>
        <label className="form-field form-field--wide">
          <span>Payment Method</span>
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            {PAYMENT_METHODS.map((m) => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </label>
        <label className="form-field form-field--wide">
          <span>Amount to Pay (₹)</span>
          <input
            type="number"
            min="0.01"
            max={initialAmount || order.total_amount}
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            autoFocus
          />
        </label>
        <label className="form-field form-field--wide">
          <span>Provider Reference <em>(UPI ID / Card Slip Auth)</em></span>
          <input
            type="text"
            placeholder="e.g. UPI-9281729381"
            value={refCode}
            onChange={(e) => setRefCode(e.target.value)}
          />
        </label>
        <label className="form-field form-field--wide">
          <span>Payment Note <em>optional</em></span>
          <input
            type="text"
            placeholder="Counter notes or receipt memo"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        {error && (
          <div className="form-error form-field--wide">
            <Icon name="alert" size={14} />
            <span>{error}</span>
          </div>
        )}
        <div className="form-actions form-field--wide">
          <button type="button" className="button button--secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="button button--primary" disabled={busy}>
            {busy ? "Recording…" : "Capture Payment"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Refund Modal                                                               */
/* -------------------------------------------------------------------------- */
function RefundModal({ order, onClose, onSave }) {
  const capturedPayments = useMemo(() => {
    return (order.payments || []).filter((p) => p.status === "captured");
  }, [order.payments]);

  const [paymentId, setPaymentId] = useState(capturedPayments[0]?.id || "");
  const [amount, setAmount] = useState(capturedPayments[0]?.amount || 0);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const selectedPayment = capturedPayments.find((p) => p.id === Number(paymentId));

  useEffect(() => {
    if (selectedPayment) {
      setAmount(selectedPayment.amount);
    }
  }, [selectedPayment]);

  const submit = async (e) => {
    e.preventDefault();
    if (!paymentId) return;
    const num = parseFloat(amount);
    if (!num || num <= 0) {
      setError("Please enter a valid refund amount.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave(selectedPayment, {
        amount: num,
        reason: reason.trim() || "Customer refund"
      });
      onClose();
    } catch (err) {
      setError(err.message || "Refund could not be processed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`Process Refund · ${order.order_number}`} description="Issue a verified refund linked to an earlier captured payment." onClose={onClose}>
      <form className="form-grid" onSubmit={submit}>
        <label className="form-field form-field--wide">
          <span>Select Payment to Refund</span>
          <select value={paymentId} onChange={(e) => setPaymentId(e.target.value)}>
            {capturedPayments.map((p) => (
              <option key={p.id} value={p.id}>
                #{p.id} · {p.method.toUpperCase()} · {money(p.amount)} ({dateTime(p.created_at)})
              </option>
            ))}
          </select>
        </label>
        <label className="form-field form-field--wide">
          <span>Refund Amount (₹)</span>
          <input
            type="number"
            min="0.01"
            max={selectedPayment?.amount || 99999}
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <label className="form-field form-field--wide">
          <span>Refund Reason</span>
          <input
            type="text"
            placeholder="Cancellation, order adjustment, or quality issue"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {error && (
          <div className="form-error form-field--wide">
            <Icon name="alert" size={14} />
            <span>{error}</span>
          </div>
        )}
        <div className="form-actions form-field--wide">
          <button type="button" className="button button--secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="button button--danger" disabled={busy}>
            {busy ? "Refunding…" : "Issue Refund"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Main Orders & Fulfilment Page Component                                    */
/* -------------------------------------------------------------------------- */
export default function OrdersPage({ data, search, quickAction, onConsumeQuickAction }) {
  const {
    orders,
    products,
    customers,
    createOrder,
    getOrder,
    transitionOrder,
    addPayment,
    refundPayment,
    createCustomer
  } = data;
  const { user } = useAuth();
  const canManage = canManageOperations(user);
  const notify = useToast();

  const [activeTab, setActiveTab] = useState("all");
  const [modal, setModal] = useState(null);
  const [busyOrderId, setBusyOrderId] = useState(null);

  // Quick Action trigger from global topbar "+"
  useEffect(() => {
    if (quickAction?.page === "orders") {
      setModal({ kind: "billing" });
      onConsumeQuickAction?.(quickAction.id);
    }
  }, [quickAction, onConsumeQuickAction]);

  // Operational metrics
  const metrics = useMemo(() => {
    const totalActive = orders.filter((o) => ["confirmed", "in_progress", "ready"].includes(o.status)).length;
    const inKitchen = orders.filter((o) => o.status === "in_progress").length;
    const readyCounter = orders.filter((o) => o.status === "ready").length;
    const completedToday = orders.filter((o) => o.status === "completed").length;
    return { totalActive, inKitchen, readyCounter, completedToday };
  }, [orders]);

  // Filtered orders list
  const filteredOrders = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return orders.filter((order) => {
      const matchesTab = activeTab === "all" || order.status === activeTab;
      const customerName = order.customer?.full_name || "";
      const customerPhone = order.customer?.phone || "";
      const matchesSearch =
        !needle ||
        order.order_number.toLowerCase().includes(needle) ||
        customerName.toLowerCase().includes(needle) ||
        customerPhone.toLowerCase().includes(needle);
      return matchesTab && matchesSearch;
    });
  }, [orders, activeTab, search]);

  // Handle Save Order from POS Billing Modal
  const handleSaveOrder = async (orderPayload, confirmImmediately = false) => {
    const created = await createOrder(orderPayload);
    if (confirmImmediately) {
      await transitionOrder(created, "confirmed", "Confirmed at counter during billing.");
      notify(`Order ${created.order_number} confirmed and sent to kitchen.`, { title: "Order Confirmed" });
    } else {
      notify(`Draft order ${created.order_number} created.`, { title: "Draft Saved" });
    }
  };

  // Status transitions
  const handleTransition = async (order, nextStatus) => {
    setBusyOrderId(order.id);
    try {
      await transitionOrder(order, nextStatus);
      const labels = {
        confirmed: "Confirmed & inventory reserved",
        in_progress: "Moved to kitchen production",
        ready: "Ready at the counter",
        completed: "Marked as completed",
        cancelled: "Cancelled & inventory restored"
      };
      notify(`${order.order_number}: ${labels[nextStatus] || nextStatus}`, { title: "Status Updated" });
    } catch (err) {
      notify(err.message || "Failed to update order status.", { tone: "error" });
    } finally {
      setBusyOrderId(null);
    }
  };

  // Open detailed receipt
  const openReceipt = async (order) => {
    try {
      const detailed = await getOrder(order);
      setModal({ kind: "receipt", order: detailed });
    } catch {
      setModal({ kind: "receipt", order });
    }
  };

  // Open payment modal
  const openPayment = (order, defaultAmount) => {
    setModal({ kind: "payment", order, initialAmount: defaultAmount });
  };

  // Save payment
  const handleCapturePayment = async (fields) => {
    await addPayment(modal.order, fields);
    notify(`Payment of ${money(fields.amount)} captured for ${modal.order.order_number}.`, { title: "Payment Recorded" });
  };

  // Save refund
  const handleProcessRefund = async (payment, fields) => {
    await refundPayment(modal.order, payment, fields);
    notify(`Refund of ${money(fields.amount)} issued for ${modal.order.order_number}.`, { title: "Refund Issued" });
  };

  return (
    <div className="page page--orders">
      <PageHeading description="Real-time order fulfilment, visual cake POS billing, and customer receipt management." />

      {/* Operational Fulfilment Summary Metrics */}
      <div className="inventory-summary" style={{ marginBottom: "16px" }}>
        <GlassPanel>
          <span className="summary-icon summary-icon--rose"><Icon name="receipt" size={18} /></span>
          <div>
            <span>In Fulfilment</span>
            <strong>{metrics.totalActive}</strong>
          </div>
        </GlassPanel>
        <GlassPanel>
          <span className="summary-icon summary-icon--blue"><Icon name="coffee" size={18} /></span>
          <div>
            <span>Kitchen Queue</span>
            <strong>{metrics.inKitchen}</strong>
          </div>
        </GlassPanel>
        <GlassPanel>
          <span className="summary-icon summary-icon--mint"><Icon name="check" size={18} /></span>
          <div>
            <span>Ready at Counter</span>
            <strong>{metrics.readyCounter}</strong>
          </div>
        </GlassPanel>
      </div>

      {/* Filter Tabs & Counter Action Bar */}
      <div className="filter-bar">
        {ORDER_TABS.map((tab) => {
          const count = tab.id === "all" ? orders.length : orders.filter((o) => o.status === tab.id).length;
          return (
            <button
              key={tab.id}
              type="button"
              className={`filter-chip ${activeTab === tab.id ? "is-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label} ({count})
            </button>
          );
        })}
        <span className="result-count">{filteredOrders.length} orders</span>
        {canManage && (
          <button
            type="button"
            className="button button--primary button--small"
            style={{ marginLeft: "auto" }}
            onClick={() => setModal({ kind: "billing" })}
          >
            <Icon name="plus" size={14} /> New Order & POS
          </button>
        )}
      </div>

      {/* Orders Data Table */}
      {filteredOrders.length ? (
        <GlassPanel className="data-panel" padding={false}>
          <div className="data-table-wrap">
            <table className="orders-table">
              <thead>
                <tr>
                  <th>Order #</th>
                  <th>Customer</th>
                  <th>Fulfillment</th>
                  <th>Total Amount</th>
                  <th>Payment</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredOrders.map((order) => {
                  const allowed = allowedTransitions[order.status] || [];
                  const isBusy = busyOrderId === order.id;

                  return (
                    <tr key={order.id}>
                      <td>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => openReceipt(order)}
                          style={{ fontWeight: 700 }}
                        >
                          <Icon name="receipt" size={14} /> {order.order_number}
                        </button>
                      </td>
                      <td>
                        <div className="customer-cell">
                          <strong>{order.customer?.full_name || "Walk-in Guest"}</strong>
                          <small>{order.customer?.phone || dateTime(order.created_at)}</small>
                        </div>
                      </td>
                      <td>
                        <div style={{ display: "grid", gap: "2px" }}>
                          <span style={{ textTransform: "capitalize", fontSize: "11px", fontWeight: 600 }}>
                            {order.fulfillment_type === "delivery" ? "Home Delivery" : "Pickup"}
                          </span>
                          <small style={{ color: "var(--muted)", fontSize: "10px" }}>
                            {order.pickup_at ? dateTime(order.pickup_at) : (order.delivery_address || "At counter")}
                          </small>
                        </div>
                      </td>
                      <td className="cell-money">{money(order.total_amount)}</td>
                      <td>
                        <span className={`payment-status payment-status--${order.payment_status}`}>
                          {order.payment_status}
                        </span>
                      </td>
                      <td>
                        <StatusPill status={order.status} />
                      </td>
                      <td>
                        <div className="row-actions">
                          {/* Lifecycle Advancement */}
                          {canManage && order.status === "draft" && (
                            <button
                              type="button"
                              className="button button--secondary button--small"
                              onClick={() => handleTransition(order, "confirmed")}
                              disabled={isBusy}
                              title="Confirm order & allocate stock"
                            >
                              Confirm
                            </button>
                          )}
                          {canManage && order.status === "confirmed" && (
                            <button
                              type="button"
                              className="button button--secondary button--small"
                              onClick={() => handleTransition(order, "in_progress")}
                              disabled={isBusy}
                              title="Send to kitchen baking"
                            >
                              Kitchen
                            </button>
                          )}
                          {canManage && order.status === "in_progress" && (
                            <button
                              type="button"
                              className="button button--secondary button--small"
                              onClick={() => handleTransition(order, "ready")}
                              disabled={isBusy}
                              title="Mark ready at counter"
                            >
                              Ready
                            </button>
                          )}
                          {canManage && order.status === "ready" && (
                            <button
                              type="button"
                              className="button button--primary button--small"
                              onClick={() => handleTransition(order, "completed")}
                              disabled={isBusy}
                              title="Hand over to customer"
                            >
                              Complete
                            </button>
                          )}

                          {/* Quick Payment Button if unpaid / partial */}
                          {canManage && order.payment_status !== "paid" && order.status !== "cancelled" && (
                            <button
                              type="button"
                              className="table-icon"
                              onClick={() => openPayment(order)}
                              title="Record payment"
                              aria-label={`Pay ${order.order_number}`}
                            >
                              <Icon name="card" size={15} />
                            </button>
                          )}

                          {/* View Receipt / Invoice */}
                          <button
                            type="button"
                            className="table-icon"
                            onClick={() => openReceipt(order)}
                            title="View / Print Bill"
                            aria-label={`View bill for ${order.order_number}`}
                          >
                            <Icon name="printer" size={15} />
                          </button>

                          {/* Refund Option */}
                          {canManage && order.payment_status !== "unpaid" && (
                            <button
                              type="button"
                              className="table-icon"
                              onClick={() => setModal({ kind: "refund", order })}
                              title="Issue refund"
                              aria-label={`Refund ${order.order_number}`}
                            >
                              <Icon name="trend" size={15} />
                            </button>
                          )}

                          {/* Cancel Option */}
                          {canManage && allowed.includes("cancelled") && (
                            <button
                              type="button"
                              className="table-icon"
                              onClick={() => setModal({ kind: "cancel", order })}
                              title="Cancel order"
                              aria-label={`Cancel ${order.order_number}`}
                            >
                              <Icon name="close" size={15} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </GlassPanel>
      ) : (
        <GlassPanel>
          <EmptyState
            icon="receipt"
            title="No orders found"
            description={
              activeTab !== "all"
                ? `There are no orders with status '${activeTab}'.`
                : "No customer orders recorded yet. Start a new order from the counter POS."
            }
            action={
              canManage ? (
                <button
                  type="button"
                  className="button button--primary"
                  onClick={() => setModal({ kind: "billing" })}
                >
                  Create New Order
                </button>
              ) : null
            }
          />
        </GlassPanel>
      )}

      {/* POS Billing Counter Modal */}
      {modal?.kind === "billing" && (
        <OrderBillingModal
          products={products}
          customers={customers}
          onClose={() => setModal(null)}
          onSave={handleSaveOrder}
          onQuickCustomerCreate={createCustomer}
        />
      )}

      {/* Receipt & Printable Bill Modal */}
      {modal?.kind === "receipt" && (
        <OrderReceiptModal
          order={modal.order}
          onClose={() => setModal(null)}
          onRecordPayment={(ord, bal) => setModal({ kind: "payment", order: ord, initialAmount: bal })}
        />
      )}

      {/* Payment Capture Modal */}
      {modal?.kind === "payment" && (
        <PaymentCaptureModal
          order={modal.order}
          initialAmount={modal.initialAmount}
          onClose={() => setModal(null)}
          onSave={handleCapturePayment}
        />
      )}

      {/* Refund Modal */}
      {modal?.kind === "refund" && (
        <RefundModal
          order={modal.order}
          onClose={() => setModal(null)}
          onSave={handleProcessRefund}
        />
      )}

      {/* Cancel Order Dialog */}
      {modal?.kind === "cancel" && (
        <ConfirmDialog
          title={`Cancel ${modal.order.order_number}?`}
          description="Cancelling this order will stop production. If the order was confirmed, its reserved cake stock will be automatically restored to the inventory ledger."
          confirmLabel="Cancel Order"
          tone="danger"
          onClose={() => setModal(null)}
          onConfirm={async () => {
            await handleTransition(modal.order, "cancelled");
            setModal(null);
          }}
        />
      )}
    </div>
  );
}
