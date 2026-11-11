/**
 * Rutas de la aplicacion con carga diferida.
 *
 * Cada pantalla se descarga solo cuando se visita. Asi el cobrador no baja el
 * codigo del dashboard ni el del cotizador, que nunca usa.
 */

import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { lazy, Suspense, type ReactNode } from "react";

import { useAuth } from "@/auth/useAuth";
import { homeFor } from "@/auth/home";
import { Spinner } from "@/components/ui";
import { AppLayout } from "@/layouts/AppLayout";
import { LoginPage } from "@/pages/LoginPage";

// Pantallas cargadas bajo demanda.
const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({ default: module.DashboardPage })),
);
const ClientsPage = lazy(() =>
  import("@/pages/ClientsPage").then((module) => ({ default: module.ClientsPage })),
);
const ClientNewPage = lazy(() =>
  import("@/pages/ClientNewPage").then((module) => ({ default: module.ClientNewPage })),
);
const ClientDetailPage = lazy(() =>
  import("@/pages/ClientDetailPage").then((module) => ({ default: module.ClientDetailPage })),
);
const LoansPage = lazy(() =>
  import("@/pages/LoansPage").then((module) => ({ default: module.LoansPage })),
);
const LoanNewPage = lazy(() =>
  import("@/pages/LoanNewPage").then((module) => ({ default: module.LoanNewPage })),
);
const LoanDetailPage = lazy(() =>
  import("@/pages/LoanDetailPage").then((module) => ({ default: module.LoanDetailPage })),
);
const PaymentsPage = lazy(() =>
  import("@/pages/PaymentsPage").then((module) => ({ default: module.PaymentsPage })),
);
const RoutesPage = lazy(() =>
  import("@/pages/RoutesPage").then((module) => ({ default: module.RoutesPage })),
);
const RouteDetailPage = lazy(() =>
  import("@/pages/RouteDetailPage").then((module) => ({ default: module.RouteDetailPage })),
);
const AuditPage = lazy(() =>
  import("@/pages/AuditPage").then((module) => ({ default: module.AuditPage })),
);

/** Envuelve una pantalla con un indicador mientras se descarga su codigo. */
function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Spinner label="Cargando…" />}>{children}</Suspense>;
}

/** Exige sesion iniciada; si no la hay, manda al login recordando el destino. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner label="Verificando sesión…" />;

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}

/** Exige uno de los roles indicados. El Administrador siempre pasa. */
function RequireRole({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { user } = useAuth();

  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "admin" || roles.includes(user.role)) return <>{children}</>;

  return <Navigate to={homeFor(user.role)} replace />;
}

/** Redirige a la pantalla inicial del usuario autenticado. */
function HomeRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homeFor(user.role)} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<HomeRedirect />} />

        <Route
          path="dashboard"
          element={
            <RequireRole roles={["admin"]}>
              <Page>
                <DashboardPage />
              </Page>
            </RequireRole>
          }
        />

        <Route
          path="clientes"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <ClientsPage />
              </Page>
            </RequireRole>
          }
        />
        <Route
          path="clientes/nuevo"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <ClientNewPage />
              </Page>
            </RequireRole>
          }
        />
        <Route
          path="clientes/:id"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <ClientDetailPage />
              </Page>
            </RequireRole>
          }
        />

        <Route
          path="prestamos"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <LoansPage />
              </Page>
            </RequireRole>
          }
        />
        <Route
          path="prestamos/nuevo"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <LoanNewPage />
              </Page>
            </RequireRole>
          }
        />
        <Route
          path="prestamos/:id"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <LoanDetailPage />
              </Page>
            </RequireRole>
          }
        />

        <Route
          path="pagos"
          element={
            <RequireRole roles={["prestamista"]}>
              <Page>
                <PaymentsPage />
              </Page>
            </RequireRole>
          }
        />

        <Route
          path="rutas"
          element={
            <RequireRole roles={["cobrador"]}>
              <Page>
                <RoutesPage />
              </Page>
            </RequireRole>
          }
        />
        <Route
          path="rutas/:id"
          element={
            <RequireRole roles={["cobrador"]}>
              <Page>
                <RouteDetailPage />
              </Page>
            </RequireRole>
          }
        />

        <Route
          path="auditoria"
          element={
            <RequireRole roles={["admin"]}>
              <Page>
                <AuditPage />
              </Page>
            </RequireRole>
          }
        />

        <Route path="*" element={<HomeRedirect />} />
      </Route>
    </Routes>
  );
}
