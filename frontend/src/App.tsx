/**
 * Definición de rutas y protección por sesión.
 *
 * El acceso a cada módulo se decide por rol. El cobrador entra a su ruta del
 * día; el prestamista a clientes y préstamos; el administrador a todo.
 */

import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "@/auth/useAuth";
import { homeFor } from "@/auth/home";
import { Spinner } from "@/components/ui";
import { AppLayout } from "@/layouts/AppLayout";
import { AuditPage } from "@/pages/AuditPage";
import { ClientDetailPage } from "@/pages/ClientDetailPage";
import { ClientNewPage } from "@/pages/ClientNewPage";
import { ClientsPage } from "@/pages/ClientsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoanDetailPage } from "@/pages/LoanDetailPage";
import { LoanNewPage } from "@/pages/LoanNewPage";
import { LoansPage } from "@/pages/LoansPage";
import { LoginPage } from "@/pages/LoginPage";
import { PaymentsPage } from "@/pages/PaymentsPage";
import { RouteDetailPage } from "@/pages/RouteDetailPage";
import { RoutesPage } from "@/pages/RoutesPage";

/** Exige sesión iniciada; si no la hay, manda al login recordando el destino. */
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
              <DashboardPage />
            </RequireRole>
          }
        />

        <Route
          path="clientes"
          element={
            <RequireRole roles={["prestamista"]}>
              <ClientsPage />
            </RequireRole>
          }
        />
        <Route
          path="clientes/nuevo"
          element={
            <RequireRole roles={["prestamista"]}>
              <ClientNewPage />
            </RequireRole>
          }
        />
        <Route
          path="clientes/:id"
          element={
            <RequireRole roles={["prestamista"]}>
              <ClientDetailPage />
            </RequireRole>
          }
        />

        <Route
          path="prestamos"
          element={
            <RequireRole roles={["prestamista"]}>
              <LoansPage />
            </RequireRole>
          }
        />
        <Route
          path="prestamos/nuevo"
          element={
            <RequireRole roles={["prestamista"]}>
              <LoanNewPage />
            </RequireRole>
          }
        />
        <Route
          path="prestamos/:id"
          element={
            <RequireRole roles={["prestamista"]}>
              <LoanDetailPage />
            </RequireRole>
          }
        />

        <Route
          path="pagos"
          element={
            <RequireRole roles={["prestamista"]}>
              <PaymentsPage />
            </RequireRole>
          }
        />

        <Route
          path="rutas"
          element={
            <RequireRole roles={["cobrador"]}>
              <RoutesPage />
            </RequireRole>
          }
        />
        <Route
          path="rutas/:id"
          element={
            <RequireRole roles={["cobrador"]}>
              <RouteDetailPage />
            </RequireRole>
          }
        />

        <Route
          path="auditoria"
          element={
            <RequireRole roles={["admin"]}>
              <AuditPage />
            </RequireRole>
          }
        />

        <Route path="*" element={<HomeRedirect />} />
      </Route>
    </Routes>
  );
}
