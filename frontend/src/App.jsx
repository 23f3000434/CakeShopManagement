import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "./context/AuthContext";
import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { GlassPanel, LoadingPanel } from "./components/Primitives";
import { Icon } from "./components/Icon";
import { useDebouncedValue } from "./hooks/useDebouncedValue";
import { useOperationsData } from "./hooks/useOperationsData";
import { useToast } from "./context/ToastContext";
import AuthScreen from "./pages/AuthScreen";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ProductsPage = lazy(() => import("./pages/ProductsPage"));
const OrdersPage = lazy(() => import("./pages/OrdersPage"));
const CustomersPage = lazy(() => import("./pages/CustomersPage"));
const InventoryPage = lazy(() => import("./pages/InventoryPage"));

const views = { dashboard: DashboardPage, products: ProductsPage, orders: OrdersPage, customers: CustomersPage, inventory: InventoryPage };

function initialPage() {
  const value = window.location.hash.replace("#", "");
  return views[value] ? value : "dashboard";
}

function Workspace() {
  const [page, setPage] = useState(initialPage);
  const [searchInput, setSearchInput] = useState("");
  const [quickAction, setQuickAction] = useState(null);
  const search = useDebouncedValue(searchInput);
  const data = useOperationsData();
  const notify = useToast();
  const Page = views[page] || DashboardPage;

  useEffect(() => {
    const onHashChange = () => setPage(initialPage());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((nextPage) => {
    window.location.hash = nextPage;
    setPage(nextPage);
    setSearchInput("");
  }, []);
  const triggerQuickAction = useCallback((currentPage) => {
    const destination = currentPage === "dashboard" ? "orders" : currentPage;
    if (destination !== currentPage) navigate(destination);
    setQuickAction({ page: destination, id: Date.now() });
  }, [navigate]);
  const consumeQuickAction = useCallback((id) => {
    setQuickAction((current) => current?.id === id ? null : current);
  }, []);
  const pendingOrderCount = useMemo(() => data.orders.filter((order) => ["confirmed", "in_progress", "ready"].includes(order.status)).length, [data.orders]);

  return <AppShell page={page} onNavigate={navigate} onQuickAction={triggerQuickAction} search={searchInput} onSearchChange={setSearchInput} lowStockCount={data.lowStock.length} pendingOrderCount={pendingOrderCount}>
    {data.status === "error" ? <GlassPanel className="api-error"><span><Icon name="alert" size={22} /></span><div><p className="eyebrow">CONNECTION NEEDS ATTENTION</p><h2>We couldn’t refresh your bakery data.</h2><p>{data.error?.message || "Check your connection and try again."}</p><button className="button button--primary" onClick={() => data.reload()}>Try again</button></div></GlassPanel> : <ErrorBoundary><Suspense fallback={<LoadingPanel label="Loading bakery records…" />}><Page data={data} search={search} onNavigate={navigate} quickAction={quickAction} onConsumeQuickAction={consumeQuickAction} /></Suspense></ErrorBoundary>}
  </AppShell>;
}

export default function App() {
  const { status } = useAuth();
  if (status === "checking") return <main className="startup-screen"><div className="startup-screen__brand"><span className="brand__mark">B</span><strong>Butterlane</strong></div><LoadingPanel label="Checking your session…" /></main>;
  if (status !== "authenticated") return <AuthScreen />;
  return <Workspace />;
}
