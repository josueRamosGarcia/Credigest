/**
 * Marco de la aplicación: barra lateral, cabecera y contenido.
 *
 * El menú se arma según el rol: el cobrador solo ve lo suyo, el prestamista no
 * ve el dashboard global ni la auditoría.
 */

import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { ROLE_LABELS } from "@/api/auth";
import { useAuth } from "@/auth/useAuth";
import { initials } from "@/lib/format";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  roles: string[];
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Inicio", icon: "◧", roles: ["cobrador"] },
  { to: "/dashboard", label: "Dashboard", icon: "▦", roles: ["admin"] },
  { to: "/clientes", label: "Clientes", icon: "◍", roles: ["prestamista"] },
  { to: "/prestamos", label: "Préstamos", icon: "▤", roles: ["prestamista"] },
  { to: "/pagos", label: "Pagos", icon: "◫", roles: ["prestamista"] },
  { to: "/rutas", label: "Rutas de cobro", icon: "◈", roles: ["cobrador"] },
  { to: "/auditoria", label: "Auditoría", icon: "◉", roles: ["admin"] },
];

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (!user) return false;
    // El Administrador ve todo.
    if (user.role === "admin") return true;
    return item.roles.includes(user.role);
  });

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white md:flex md:flex-col">
        <div className="border-b border-slate-200 px-5 py-5">
          <p className="text-lg font-semibold tracking-tight text-brand-700">
            Credigest
          </p>
          <p className="truncate text-xs text-slate-500">
            {user?.tenant_name}
          </p>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`
              }
            >
              <span aria-hidden="true" className="text-base">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-3">
          <div className="flex items-center gap-3 rounded-lg px-2 py-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
              {initials(user?.full_name ?? "")}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-900">
                {user?.full_name}
              </p>
              <p className="truncate text-xs text-slate-500">
                {user ? ROLE_LABELS[user.role] : ""}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
          >
            Cerrar sesión
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior para móvil. */}
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <p className="font-semibold text-brand-700">Credigest</p>
          <button
            type="button"
            onClick={handleLogout}
            className="text-sm text-slate-600"
          >
            Salir
          </button>
        </header>

        <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-2 py-2 md:hidden">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-600"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
