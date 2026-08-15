import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { Icon } from "../components/Icon";
import { ConfirmDialog, Modal } from "../components/Modal";
import { EmptyState, GlassPanel, PageHeading } from "../components/Primitives";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import { initials, money } from "../lib/formatters";
import { canManageOperations } from "../lib/permissions";

const emptyCustomer = { full_name: "", email: "", phone: "", address: "", notes: "", is_active: true };

const CustomerCard = memo(function CustomerCard({ customer, onEdit, onArchive, canManage }) {
  return <GlassPanel className={`customer-card ${customer.is_active ? "" : "customer-card--archived"}`}><div className="customer-card__top"><span className="customer-card__avatar">{initials(customer.full_name)}</span><div><strong>{customer.full_name}</strong><span>{customer.email || customer.phone || "No contact details"}</span></div>{canManage ? <button className="table-icon" onClick={() => onEdit(customer)} aria-label={`Edit ${customer.full_name}`}><Icon name="edit" size={16} /></button> : null}</div><div className="customer-card__detail"><span><Icon name="receipt" size={13} /> {customer.completed_order_count || 0} completed orders</span><span><Icon name="trend" size={13} /> {money(customer.total_spent)}</span></div><div className="customer-card__footer"><span>{customer.is_active ? "Active" : "Archived"}</span>{canManage && customer.is_active ? <button className="text-button text-button--muted" onClick={() => onArchive(customer)}>Archive</button> : null}</div></GlassPanel>;
});

function CustomerForm({ customer, onClose, onSave }) {
  const [form, setForm] = useState(customer || emptyCustomer); const [error, setError] = useState(null); const [busy, setBusy] = useState(false); const nameRef = useRef(null);
  const update = (event) => { const { name, value, type, checked } = event.target; setForm((current) => ({ ...current, [name]: type === "checkbox" ? checked : value })); };
  const submit = async (event) => { event.preventDefault(); if (!form.full_name.trim()) return setError("A customer name is required."); setBusy(true); setError(null); try { await onSave({ full_name: form.full_name.trim(), email: (form.email || "").trim() || null, phone: (form.phone || "").trim() || null, address: (form.address || "").trim() || null, notes: (form.notes || "").trim() || null, is_active: Boolean(form.is_active) }); onClose(); } catch (reason) { setError(reason instanceof ApiError ? reason.message : "This customer could not be saved."); } finally { setBusy(false); } };
  return <Modal title={customer ? "Update customer details" : "Add a customer"} description="Keep contact details, delivery information, and useful order notes together." onClose={onClose} size="wide"><form className="form-grid" onSubmit={submit}>
    <label className="form-field form-field--wide"><span>Full name</span><input ref={nameRef} name="full_name" value={form.full_name} onChange={update} placeholder="e.g. Maya Nair" autoFocus /></label><label className="form-field"><span>Email <em>optional</em></span><input name="email" type="email" value={form.email || ""} onChange={update} placeholder="maya@example.com" /></label><label className="form-field"><span>Phone <em>optional</em></span><input name="phone" value={form.phone || ""} onChange={update} placeholder="+91…" /></label><label className="form-field form-field--wide"><span>Address <em>optional</em></span><textarea name="address" value={form.address || ""} onChange={update} placeholder="Useful for delivery orders…" /></label><label className="form-field form-field--wide"><span>Customer notes <em>optional</em></span><textarea name="notes" value={form.notes || ""} onChange={update} placeholder="Dietary notes, preferred style, birthday pattern…" /></label><label className="toggle-row form-field--wide"><span><strong>Keep customer active</strong><small>Archiving retains their history without offering them in new orders.</small></span><input name="is_active" type="checkbox" checked={Boolean(form.is_active)} onChange={update} /><i /></label>{error ? <div className="form-error form-field--wide"><Icon name="alert" size={15} />{error}</div> : null}<div className="form-actions form-field--wide"><button type="button" className="button button--secondary" onClick={onClose}>Cancel</button><button className="button button--primary" disabled={busy}>{busy ? "Saving…" : customer ? "Save changes" : "Add customer"}</button></div>
  </form></Modal>;
}

export default function CustomersPage({ data, search, quickAction, onConsumeQuickAction }) {
  const { customers, createCustomer, updateCustomer, archiveCustomer } = data;
  const { user } = useAuth();
  const canManage = canManageOperations(user);
  const [modal, setModal] = useState(null); const [showArchived, setShowArchived] = useState(false); const [busy, setBusy] = useState(false); const notify = useToast();
  useEffect(() => {
    if (quickAction?.page === "customers") {
      if (canManage) setModal({ kind: "new" });
      onConsumeQuickAction?.(quickAction.id);
    }
  }, [quickAction, onConsumeQuickAction, canManage]);
  const filtered = useMemo(() => { const needle = search.trim().toLowerCase(); return customers.filter((customer) => (showArchived || customer.is_active) && (!needle || [customer.full_name, customer.email, customer.phone].join(" ").toLowerCase().includes(needle))); }, [customers, search, showArchived]);
  const save = async (fields) => { if (modal?.kind === "edit") { await updateCustomer(modal.customer, fields); notify(`${fields.full_name}'s details are up to date.`, { title: "Customer updated" }); } else { await createCustomer(fields); notify(`${fields.full_name} has been added to your customer book.`, { title: "Customer added" }); } };
  const confirmArchive = async () => { setBusy(true); try { await archiveCustomer(modal.customer); notify(`${modal.customer.full_name} is archived; their order history is retained.`, { title: "Customer archived" }); setModal(null); } catch (error) { notify(error.message, { tone: "error" }); } finally { setBusy(false); } };
  return <div className="page page--customers"><PageHeading description="Keep contact details, order history, and customer notes together." />
    <div className="filter-bar"><button className={`filter-chip ${!showArchived ? "is-active" : ""}`} onClick={() => setShowArchived(false)}>Active customers</button><button className={`filter-chip ${showArchived ? "is-active" : ""}`} onClick={() => setShowArchived(true)}>Including archived</button><span className="result-count">{filtered.length} customers</span></div>
    {filtered.length ? <div className="customer-grid">{filtered.map((customer) => <CustomerCard key={customer.id} customer={customer} onEdit={(item) => setModal({ kind: "edit", customer: item })} onArchive={(item) => setModal({ kind: "archive", customer: item })} canManage={canManage} />)}</div> : <GlassPanel><EmptyState icon="users" title="No customers match this view" description={canManage ? "Add a customer or clear the search to find their record." : "Clear the search to find a customer record."} action={canManage ? <button className="button button--primary" onClick={() => setModal({ kind: "new" })}>Add a customer</button> : null} /></GlassPanel>}
    {modal?.kind === "new" || modal?.kind === "edit" ? <CustomerForm customer={modal.kind === "edit" ? modal.customer : null} onClose={() => setModal(null)} onSave={save} /> : null}{modal?.kind === "archive" ? <ConfirmDialog title={`Archive ${modal.customer.full_name}?`} description="They will not appear in new-order selections, but their historical information remains safely retained." confirmLabel="Archive customer" onClose={() => setModal(null)} onConfirm={confirmArchive} busy={busy} /> : null}
  </div>;
}
