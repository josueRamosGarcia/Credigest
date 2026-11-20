/**
 * Pantalla de Configuración y Usuarios (CU-02, RF-03 a RF-12).
 *
 * Permite al Administrador gestionar las cuentas de acceso de su financiera,
 * asignar roles y permisos granulares, y configurar los parámetros globales
 * para nuevos préstamos.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { ROLE_LABELS } from "@/api/auth";
import { SCHEME_LABELS } from "@/api/loans";
import type { LoanScheme, Role } from "@/api/types";
import {
  changeUserStatus,
  createUser,
  getSystemSettings,
  listUsers,
  PERMISSION_LABELS,
  resetUserPassword,
  type UserAccount,
  updateSystemSettings,
  updateUser,
} from "@/api/users";
import { useAuth } from "@/auth/useAuth";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Spinner,
} from "@/components/ui";
import { formatDateTime, formatRate, percentToRate } from "@/lib/format";

const PAGE_SIZE = 20;
const EDITABLE_PERMISSIONS = ["edit_rate", "cancel_payment"] as const;

export function SettingsPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();

  // --- Estado de filtros de usuarios ---
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<Role | "">("");
  const [statusFilter, setStatusFilter] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);

  // --- Estado del formulario de nuevo usuario ---
  const [showNewUser, setShowNewUser] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState<Role>("prestamista");
  const [password, setPassword] = useState("");
  const [permissions, setPermissions] = useState<Record<string, boolean>>({
    edit_rate: false,
    cancel_payment: false,
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [tempPasswordInfo, setTempPasswordInfo] = useState<{
    email: string;
    password: string;
  } | null>(null);

  // --- Estado de parámetros globales (borrador editable sobre el valor del servidor) ---
  const [lateFeeDraft, setLateFeeDraft] = useState<string | null>(null);
  const [schemeDraft, setSchemeDraft] = useState<LoanScheme | null>(null);
  const [graceDaysDraft, setGraceDaysDraft] = useState<string | null>(null);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSystemSettings,
  });

  const serverLateFee = settingsQuery.data
    ? (Number(settingsQuery.data.default_late_fee_rate) * 100)
        .toFixed(2)
        .replace(/\.00$/, "")
    : "10";
  const lateFeePercent = lateFeeDraft ?? serverLateFee;
  const defaultScheme =
    schemeDraft ?? settingsQuery.data?.default_scheme ?? "simple";
  const graceDays =
    graceDaysDraft ??
    (settingsQuery.data ? String(settingsQuery.data.grace_days) : "0");

  const usersQuery = useQuery({
    queryKey: ["users", { search, roleFilter, statusFilter, page }],
    queryFn: () =>
      listUsers({
        search: search || undefined,
        role: roleFilter || undefined,
        is_active:
          statusFilter === "" ? undefined : statusFilter === "true",
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: (previous) => previous,
  });

  const saveSettingsMutation = useMutation({
    mutationFn: () =>
      updateSystemSettings({
        default_late_fee_rate: percentToRate(lateFeePercent),
        default_scheme: defaultScheme,
        grace_days: Number(graceDays),
        timezone: settingsQuery.data?.timezone ?? "America/Mexico_City",
      }),
    onSuccess: () => {
      setSettingsError(null);
      setSettingsSaved(true);
      setLateFeeDraft(null);
      setSchemeDraft(null);
      setGraceDaysDraft(null);
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => {
      setSettingsSaved(false);
      setSettingsError(
        err instanceof Error ? err.message : "No se pudo guardar la configuración.",
      );
    },
  });

  const createUserMutation = useMutation({
    mutationFn: () =>
      createUser({
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
        role,
        permissions: role === "prestamista" ? permissions : {},
        password: password.trim() || null,
      }),
    onSuccess: (created) => {
      setFormError(null);
      setFullName("");
      setEmail("");
      setPhone("");
      setPassword("");
      setPermissions({ edit_rate: false, cancel_payment: false });
      setShowNewUser(false);
      if (created.temporary_password) {
        setTempPasswordInfo({
          email: created.email,
          password: created.temporary_password,
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) => {
      setFormError(
        err instanceof Error ? err.message : "No se pudo crear el usuario.",
      );
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      changeUserStatus(id, is_active),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const permissionMutation = useMutation({
    mutationFn: ({
      user,
      permKey,
    }: {
      user: UserAccount;
      permKey: string;
    }) => {
      const next = {
        ...user.permissions,
        [permKey]: !user.permissions[permKey],
      };
      return updateUser(user.id, { permissions: next });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ user }: { user: UserAccount }) => resetUserPassword(user.id),
    onSuccess: (result, variables) => {
      setTempPasswordInfo({
        email: variables.user.email,
        password: result.temporary_password,
      });
    },
  });

  const handleSaveSettings = (event: FormEvent) => {
    event.preventDefault();
    setSettingsSaved(false);
    const pct = Number(lateFeePercent);
    const grace = Number(graceDays);
    if (Number.isNaN(pct) || pct < 0 || pct > 100) {
      setSettingsError("La tasa moratoria debe estar entre 0 % y 100 %.");
      return;
    }
    if (
      Number.isNaN(grace) ||
      !Number.isInteger(grace) ||
      grace < 0 ||
      grace > 90
    ) {
      setSettingsError("Los días de gracia deben ser un entero entre 0 y 90.");
      return;
    }
    saveSettingsMutation.mutate();
  };

  const handleCreateUser = (event: FormEvent) => {
    event.preventDefault();
    if (fullName.trim().length < 2) {
      setFormError("Ingresa el nombre completo del usuario.");
      return;
    }
    if (!email.includes("@")) {
      setFormError("Ingresa un correo electrónico válido.");
      return;
    }
    if (password.trim().length > 0 && password.trim().length < 10) {
      setFormError("La contraseña debe tener al menos 10 caracteres.");
      return;
    }
    createUserMutation.mutate();
  };

  const handleToggleStatus = (target: UserAccount) => {
    const actionLabel = target.is_active ? "desactivar" : "reactivar";
    const confirmed = window.confirm(
      `¿Seguro que deseas ${actionLabel} la cuenta de ${target.full_name}?`,
    );
    if (!confirmed) return;
    statusMutation.mutate({ id: target.id, is_active: !target.is_active });
  };

  const handleResetPassword = (target: UserAccount) => {
    const confirmed = window.confirm(
      `¿Generar una contraseña temporal nueva para ${target.full_name}? Se cerrarán sus sesiones activas.`,
    );
    if (!confirmed) return;
    resetPasswordMutation.mutate({ user: target });
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Configuración y usuarios"
        description="Administra los parámetros globales de la financiera y las cuentas de tu equipo."
        actions={
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              setShowNewUser((prev) => !prev);
              setFormError(null);
            }}
          >
            {showNewUser ? "Cancelar alta" : "Nuevo usuario"}
          </button>
        }
      />

      {tempPasswordInfo && (
        <Alert tone="warning">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-semibold">
                Contraseña temporal para {tempPasswordInfo.email}
              </p>
              <p className="mt-1">
                Comparte esta clave de forma segura con el usuario:{" "}
                <code className="rounded bg-amber-100 px-2 py-0.5 font-mono font-bold">
                  {tempPasswordInfo.password}
                </code>
              </p>
            </div>
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={() => setTempPasswordInfo(null)}
            >
              Ocultar
            </button>
          </div>
        </Alert>
      )}

      {/* Parámetros globales del sistema (RF-09 a RF-12) */}
      <Card>
        <h2 className="text-base font-semibold text-slate-900">
          Parámetros globales del sistema
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          Estos valores se aplican por defecto a los préstamos nuevos. Los préstamos
          ya aprobados conservan sus condiciones congeladas (RN-06).
        </p>

        {settingsQuery.isLoading ? (
          <Spinner label="Cargando parámetros…" />
        ) : settingsQuery.isError ? (
          <ErrorState
            message="No se pudieron cargar los parámetros del sistema."
            onRetry={() => settingsQuery.refetch()}
          />
        ) : (
          <form
            onSubmit={handleSaveSettings}
            className="mt-4 grid gap-4 sm:grid-cols-3"
          >
            <div>
              <label
                htmlFor="late-fee-percent"
                className="label"
              >
                Tasa moratoria mensual (%)
              </label>
              <input
                id="late-fee-percent"
                type="number"
                step="0.01"
                min="0"
                max="100"
                className="input"
                value={lateFeePercent}
                onChange={(e) => setLateFeeDraft(e.target.value)}
              />
              {settingsQuery.data && (
                <p className="mt-1 text-xs text-slate-500">
                  Actual:{" "}
                  {formatRate(settingsQuery.data.default_late_fee_rate)} mensual
                </p>
              )}
            </div>

            <div>
              <label htmlFor="default-scheme" className="label">
                Esquema de cálculo predeterminado
              </label>
              <select
                id="default-scheme"
                className="input"
                value={defaultScheme}
                onChange={(e) => setSchemeDraft(e.target.value as LoanScheme)}
              >
                {(Object.keys(SCHEME_LABELS) as LoanScheme[]).map((key) => (
                  <option key={key} value={key}>
                    {SCHEME_LABELS[key]}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="grace-days" className="label">
                Días de gracia antes de mora
              </label>
              <input
                id="grace-days"
                type="number"
                min="0"
                max="90"
                className="input"
                value={graceDays}
                onChange={(e) => setGraceDaysDraft(e.target.value)}
              />
            </div>

            {settingsError && (
              <div className="sm:col-span-3">
                <Alert tone="error">{settingsError}</Alert>
              </div>
            )}

            {settingsSaved && (
              <div className="sm:col-span-3">
                <Alert tone="success">
                  Parámetros globales actualizados correctamente.
                </Alert>
              </div>
            )}

            <div className="sm:col-span-3 flex justify-end">
              <button
                type="submit"
                className="btn-primary"
                disabled={saveSettingsMutation.isPending}
              >
                {saveSettingsMutation.isPending
                  ? "Guardando…"
                  : "Guardar parámetros"}
              </button>
            </div>
          </form>
        )}
      </Card>

      {/* Formulario de alta de usuario (CU-02) */}
      {showNewUser && (
        <Card>
          <h2 className="text-base font-semibold text-slate-900">
            Crear nuevo usuario
          </h2>
          <form
            onSubmit={handleCreateUser}
            className="mt-4 grid gap-4 sm:grid-cols-2"
          >
            <div>
              <label htmlFor="user-fullname" className="label">
                Nombre completo
              </label>
              <input
                id="user-fullname"
                type="text"
                required
                className="input"
                placeholder="Ej. María López"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="user-email" className="label">
                Correo electrónico
              </label>
              <input
                id="user-email"
                type="email"
                required
                className="input"
                placeholder="usuario@mifinanciera.mx"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="user-phone" className="label">
                Teléfono (opcional)
              </label>
              <input
                id="user-phone"
                type="tel"
                className="input"
                placeholder="8711234567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="user-role" className="label">
                Rol en la financiera
              </label>
              <select
                id="user-role"
                className="input"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                <option value="prestamista">Prestamista</option>
                <option value="cobrador">Cobrador</option>
                <option value="admin">Administrador</option>
              </select>
            </div>

            <div className="sm:col-span-2">
              <label htmlFor="user-password" className="label">
                Contraseña inicial (opcional, mínimo 10 caracteres)
              </label>
              <input
                id="user-password"
                type="password"
                className="input max-w-md"
                placeholder="Dejar en blanco para generar una temporal"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {role === "prestamista" && (
              <div className="sm:col-span-2">
                <p className="label">Permisos especiales (RF-05)</p>
                <div className="mt-1 flex flex-wrap gap-4">
                  {EDITABLE_PERMISSIONS.map((perm) => (
                    <label
                      key={perm}
                      className="flex items-center gap-2 text-sm text-slate-700"
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(permissions[perm])}
                        onChange={(e) =>
                          setPermissions((prev) => ({
                            ...prev,
                            [perm]: e.target.checked,
                          }))
                        }
                      />
                      {PERMISSION_LABELS[perm]}
                    </label>
                  ))}
                </div>
              </div>
            )}

            {formError && (
              <div className="sm:col-span-2">
                <Alert tone="error">{formError}</Alert>
              </div>
            )}

            <div className="sm:col-span-2 flex justify-end gap-2">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowNewUser(false)}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={createUserMutation.isPending}
              >
                {createUserMutation.isPending ? "Creando…" : "Crear usuario"}
              </button>
            </div>
          </form>
        </Card>
      )}

      {/* Listado y administración de usuarios */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          Usuarios registrados
        </h2>

        <div className="mb-4 flex flex-wrap gap-3">
          <input
            type="search"
            className="input max-w-xs"
            placeholder="Buscar por nombre o correo"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />

          <select
            className="input max-w-[180px]"
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value as Role | "");
              setPage(1);
            }}
          >
            <option value="">Todos los roles</option>
            <option value="admin">Administradores</option>
            <option value="prestamista">Prestamistas</option>
            <option value="cobrador">Cobradores</option>
          </select>

          <select
            className="input max-w-[180px]"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as "" | "true" | "false");
              setPage(1);
            }}
          >
            <option value="">Todos los estados</option>
            <option value="true">Activos</option>
            <option value="false">Inactivos</option>
          </select>
        </div>

        {(statusMutation.isError ||
          permissionMutation.isError ||
          resetPasswordMutation.isError) && (
          <div className="mb-4">
            <Alert tone="error">
              {(statusMutation.error instanceof Error &&
                statusMutation.error.message) ||
                (permissionMutation.error instanceof Error &&
                  permissionMutation.error.message) ||
                (resetPasswordMutation.error instanceof Error &&
                  resetPasswordMutation.error.message) ||
                "No se pudo completar la operación."}
            </Alert>
          </div>
        )}

        {usersQuery.isLoading && <Spinner />}

        {usersQuery.isError && (
          <ErrorState
            message={
              usersQuery.error instanceof Error
                ? usersQuery.error.message
                : "No se pudieron cargar los usuarios."
            }
            onRetry={() => usersQuery.refetch()}
          />
        )}

        {usersQuery.data && usersQuery.data.items.length === 0 && (
          <EmptyState
            title="No se encontraron usuarios"
            description="Prueba cambiando los filtros o registra un nuevo integrante."
          />
        )}

        {usersQuery.data && usersQuery.data.items.length > 0 && (
          <div className="card overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
                <tr>
                  <th className="px-4 py-3 font-medium">Usuario</th>
                  <th className="px-4 py-3 font-medium">Rol</th>
                  <th className="px-4 py-3 font-medium">Permisos</th>
                  <th className="px-4 py-3 font-medium">Último acceso</th>
                  <th className="px-4 py-3 font-medium">Estado</th>
                  <th className="px-4 py-3 font-medium text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usersQuery.data.items.map((item) => {
                  const isSelf = item.id === currentUser?.id;
                  return (
                    <tr key={item.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-900">
                          {item.full_name}
                        </p>
                        <p className="text-xs text-slate-500">{item.email}</p>
                        {item.phone && (
                          <p className="tabular text-xs text-slate-400">
                            {item.phone}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge className="bg-brand-50 text-brand-700">
                          {ROLE_LABELS[item.role]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        {item.role === "admin" ? (
                          <span className="text-xs text-slate-500">
                            Acceso total (RN-61)
                          </span>
                        ) : item.role === "cobrador" ? (
                          <span className="text-xs text-slate-500">
                            Solo cobro en ruta (RN-37)
                          </span>
                        ) : (
                          <div className="flex flex-col gap-1">
                            {EDITABLE_PERMISSIONS.map((perm) => (
                              <label
                                key={perm}
                                className="flex items-center gap-1.5 text-xs text-slate-700"
                              >
                                <input
                                  type="checkbox"
                                  checked={Boolean(item.permissions[perm])}
                                  disabled={permissionMutation.isPending}
                                  onChange={() =>
                                    permissionMutation.mutate({
                                      user: item,
                                      permKey: perm,
                                    })
                                  }
                                />
                                {PERMISSION_LABELS[perm]}
                              </label>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="tabular px-4 py-3 text-slate-600">
                        {formatDateTime(item.last_login_at)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          className={
                            item.is_active
                              ? "bg-green-100 text-green-800"
                              : "bg-slate-100 text-slate-600"
                          }
                        >
                          {item.is_active ? "Activo" : "Inactivo"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {!isSelf && (
                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              className="btn-secondary px-2.5 py-1 text-xs"
                              disabled={resetPasswordMutation.isPending}
                              onClick={() => handleResetPassword(item)}
                            >
                              Clave temporal
                            </button>
                            <button
                              type="button"
                              className="btn-secondary px-2.5 py-1 text-xs"
                              disabled={statusMutation.isPending}
                              onClick={() => handleToggleStatus(item)}
                            >
                              {item.is_active ? "Desactivar" : "Reactivar"}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {usersQuery.data && (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={usersQuery.data.total}
            onChange={setPage}
          />
        )}
      </div>
    </div>
  );
}
