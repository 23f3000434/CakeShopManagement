import { createContext, useCallback, useContext, useEffect, useReducer, useRef } from "react";
import { createPortal } from "react-dom";
import { Icon } from "../components/Icon";

const ToastContext = createContext(null);

function reducer(state, action) {
  switch (action.type) {
    case "add":
      // Newest toast comes first; cap at 4 toasts to avoid cluttering screen
      return [action.toast, ...state.filter((t) => t.id !== action.toast.id)].slice(0, 4);
    case "remove":
      return state.filter((toast) => toast.id !== action.id);
    default:
      return state;
  }
}

function ToastItem({ toast, onDismiss }) {
  const timerRef = useRef(null);
  const startTimeRef = useRef(Date.now());
  const remainingRef = useRef(toast.duration);

  const startTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    timerRef.current = setTimeout(() => {
      onDismiss(toast.id);
    }, remainingRef.current);
  }, [toast.id, onDismiss]);

  const pauseTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      const elapsed = Date.now() - startTimeRef.current;
      remainingRef.current = Math.max(1000, remainingRef.current - elapsed);
    }
  }, []);

  useEffect(() => {
    startTimer();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [startTimer]);

  const iconName = toast.tone === "error" ? "alert" : toast.tone === "warning" ? "alert" : "check";

  return (
    <div
      className={`toast toast--${toast.tone}`}
      role="status"
      onMouseEnter={pauseTimer}
      onMouseLeave={startTimer}
    >
      <span className="toast__icon">
        <Icon name={iconName} size={15} />
      </span>
      <span className="toast__copy">
        <strong>{toast.title}</strong>
        <span>{toast.message}</span>
      </span>
      <button
        className="icon-button icon-button--bare toast__close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        <Icon name="close" size={13} />
      </button>
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, dispatch] = useReducer(reducer, []);

  const notify = useCallback((message, options = {}) => {
    const id = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const tone = options.tone || "success";
    const defaultTitle = tone === "error" ? "Action needed" : tone === "warning" ? "Notice" : "Success";
    const duration = options.duration ?? (tone === "error" ? 6000 : 4200);

    const toast = {
      id,
      title: options.title || defaultTitle,
      message,
      tone,
      duration
    };

    dispatch({ type: "add", toast });
  }, []);

  const dismiss = useCallback((id) => {
    dispatch({ type: "remove", id });
  }, []);

  return (
    <ToastContext.Provider value={notify}>
      {children}
      {createPortal(
        <div className="toast-region" aria-live="polite" aria-atomic="true">
          {toasts.map((toast) => (
            <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider.");
  return context;
}
