import { useCallback, useEffect, useReducer, useRef } from "react";
import { responseData } from "../api/client";
import { useAuth } from "../context/AuthContext";

const blankState = {
  dashboard: null,
  products: [],
  customers: [],
  orders: [],
  lowStock: [],
  status: "idle",
  error: null,
  updatedAt: null
};

function entityList(payload) {
  const value = responseData(payload);
  return Array.isArray(value) ? value : Array.isArray(value?.data) ? value.data : [];
}

function pagePath(path, page) {
  const divider = path.includes("?") ? "&" : "?";
  return `${path}${divider}page=${page}&per_page=100`;
}

async function allPages(request, path) {
  const firstPayload = await request(pagePath(path, 1));
  const first = entityList(firstPayload);
  const pages = Number(firstPayload?.meta?.pages);
  if (!Number.isInteger(pages) || pages <= 1) return first;

  const records = [...first];
  for (let page = 2; page <= pages; page += 1) {
    records.push(...entityList(await request(pagePath(path, page))));
  }
  return records;
}

function financialRequestKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
}

function reducer(state, action) {
  switch (action.type) {
    case "loading": return { ...state, status: action.silent ? state.status : "loading", error: null };
    case "loaded": return { ...state, ...action.payload, status: "ready", error: null, updatedAt: new Date() };
    case "failed": return {
      ...state,
      status: action.silent && state.status === "ready" ? "ready" : "error",
      error: action.error
    };
    case "product.upsert": {
      const products = state.products.some((item) => item.id === action.product.id)
        ? state.products.map((item) => item.id === action.product.id ? action.product : item)
        : [action.product, ...state.products];
      return { ...state, products, lowStock: products.filter((item) => item.is_active && item.stock_quantity <= item.reorder_level) };
    }
    case "customer.upsert": return { ...state, customers: state.customers.some((item) => item.id === action.customer.id) ? state.customers.map((item) => item.id === action.customer.id ? action.customer : item) : [action.customer, ...state.customers] };
    case "order.upsert": return { ...state, orders: state.orders.some((item) => item.id === action.order.id) ? state.orders.map((item) => item.id === action.order.id ? action.order : item) : [action.order, ...state.orders] };
    default: return state;
  }
}

export function useOperationsData() {
  const { request, status: authStatus } = useAuth();
  const [state, dispatch] = useReducer(reducer, blankState);
  const reloadGeneration = useRef(0);

  const reload = useCallback(async ({ silent = false } = {}) => {
    const generation = ++reloadGeneration.current;
    dispatch({ type: "loading", silent });
    try {
      const [dashboard, products, customers, orders, lowStock] = await Promise.all([
        request("/dashboard"),
        allPages(request, "/products"),
        allPages(request, "/customers"),
        allPages(request, "/orders"),
        request("/inventory/low-stock")
      ]);
      if (generation !== reloadGeneration.current) return;
      dispatch({
        type: "loaded",
        payload: {
          dashboard: responseData(dashboard),
          products,
          customers,
          orders,
          lowStock: entityList(lowStock)
        }
      });
    } catch (error) {
      if (generation === reloadGeneration.current) dispatch({ type: "failed", error, silent });
    }
  }, [request]);

  useEffect(() => {
    if (authStatus === "authenticated") reload();
  }, [authStatus, reload]);

  const createProduct = useCallback(async (fields) => {
    const product = responseData(await request("/products", { method: "POST", body: fields }));
    dispatch({ type: "product.upsert", product });
    reload({ silent: true });
    return product;
  }, [request, reload]);

  const updateProduct = useCallback(async (product, fields) => {
    const updated = responseData(await request(`/products/${product.id}`, { method: "PATCH", body: { ...fields, version: product.version } }));
    dispatch({ type: "product.upsert", product: updated });
    reload({ silent: true });
    return updated;
  }, [request, reload]);

  const archiveProduct = useCallback(async (product) => {
    const updated = responseData(await request(`/products/${product.id}`, { method: "DELETE" }));
    dispatch({ type: "product.upsert", product: updated });
    reload({ silent: true });
    return updated;
  }, [request, reload]);

  const adjustStock = useCallback(async (product, fields) => {
    const updated = responseData(await request(`/products/${product.id}/stock-adjustments`, { method: "POST", body: { ...fields, version: product.version } }));
    dispatch({ type: "product.upsert", product: updated });
    reload({ silent: true });
    return updated;
  }, [request, reload]);

  const createCustomer = useCallback(async (fields) => {
    const customer = responseData(await request("/customers", { method: "POST", body: fields }));
    dispatch({ type: "customer.upsert", customer });
    return customer;
  }, [request]);

  const updateCustomer = useCallback(async (customer, fields) => {
    const updated = responseData(await request(`/customers/${customer.id}`, { method: "PATCH", body: fields }));
    dispatch({ type: "customer.upsert", customer: updated });
    return updated;
  }, [request]);

  const archiveCustomer = useCallback(async (customer) => {
    const updated = responseData(await request(`/customers/${customer.id}`, { method: "DELETE" }));
    dispatch({ type: "customer.upsert", customer: updated });
  }, [request]);

  const createOrder = useCallback(async (fields) => {
    const order = responseData(await request("/orders", { method: "POST", body: fields }));
    dispatch({ type: "order.upsert", order });
    reload({ silent: true });
    return order;
  }, [request, reload]);

  const getOrder = useCallback(async (order) => {
    const detailedOrder = responseData(await request(`/orders/${order.id}`));
    dispatch({ type: "order.upsert", order: detailedOrder });
    return detailedOrder;
  }, [request]);

  const transitionOrder = useCallback(async (order, status, note = "") => {
    const updated = responseData(await request(`/orders/${order.id}/transition`, { method: "POST", body: { status, note, version: order.version } }));
    dispatch({ type: "order.upsert", order: updated });
    reload({ silent: true });
    return updated;
  }, [request, reload]);

  const addPayment = useCallback(async (order, fields, idempotencyKey) => {
    const payload = await request(`/orders/${order.id}/payments`, {
      method: "POST",
      body: fields,
      headers: { "Idempotency-Key": idempotencyKey || financialRequestKey() }
    });
    const updatedOrder = payload?.order || responseData(payload)?.order;
    if (updatedOrder) dispatch({ type: "order.upsert", order: updatedOrder });
    reload({ silent: true });
    return payload;
  }, [request, reload]);

  const refundPayment = useCallback(async (order, payment, fields, idempotencyKey) => {
    const payload = await request(`/orders/${order.id}/payments/${payment.id}/refunds`, {
      method: "POST",
      body: fields,
      headers: { "Idempotency-Key": idempotencyKey || financialRequestKey() }
    });
    const updatedOrder = payload?.order || responseData(payload)?.order;
    if (updatedOrder) dispatch({ type: "order.upsert", order: updatedOrder });
    reload({ silent: true });
    return payload;
  }, [request, reload]);

  return { ...state, reload, createProduct, updateProduct, archiveProduct, adjustStock, createCustomer, updateCustomer, archiveCustomer, createOrder, getOrder, transitionOrder, addPayment, refundPayment };
}
