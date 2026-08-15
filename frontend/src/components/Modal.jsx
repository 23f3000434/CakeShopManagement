import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

export function Modal({ title, description, children, onClose, size = "default", labelledBy = "dialog-title" }) {
  const closeRef = useRef(null);
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    const previousFocus = document.activeElement;
    closeRef.current?.focus();
    const onKeyDown = (event) => {
      if (event.key === "Escape") onCloseRef.current?.();
      if (event.key === "Tab") {
        const controls = [...dialogRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')]
          .filter((element) => element.getClientRects().length && getComputedStyle(element).visibility !== "hidden");
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = oldOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return createPortal(
    <div className="modal-layer" role="presentation">
      <button className="modal-layer__scrim" aria-label="Close dialog" onClick={onClose} tabIndex={-1} />
      <section ref={dialogRef} className={`modal glass-panel modal--${size}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
        <header className="modal__header">
          <div><h2 id={labelledBy}>{title}</h2>{description ? <p>{description}</p> : null}</div>
          <button className="icon-button icon-button--bare" ref={closeRef} onClick={onClose} aria-label="Close dialog"><Icon name="close" size={17} /></button>
        </header>
        <div className="modal__body">{children}</div>
      </section>
    </div>,
    document.body
  );
}

export function ConfirmDialog({ title = "Please confirm", description, confirmLabel = "Confirm", tone = "danger", onConfirm, onClose, busy = false }) {
  return (
    <Modal title={title} description={description} onClose={onClose} size="small">
      <div className="confirm-note"><Icon name="alert" size={17} /><span>This action is recorded and can affect active operations.</span></div>
      <div className="form-actions">
        <button className="button button--secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
        <button className={`button button--${tone}`} type="button" onClick={onConfirm} disabled={busy}>{busy ? "Working…" : confirmLabel}</button>
      </div>
    </Modal>
  );
}
