/** Pantalla de inicio de sesión. */

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/auth/useAuth";
import { Alert, Spinner } from "@/components/ui";

const schema = z.object({
  email: z.string().min(1, "Escribe tu correo").email("El correo no es válido"),
  password: z.string().min(1, "Escribe tu contraseña"),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { login, user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  if (loading) return <Spinner label="Verificando sesión…" />;

  if (user) {
    const from = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={from} replace />;
  }

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      await login(values.email, values.password);
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(from, { replace: true });
    } catch (exc) {
      setServerError(
        exc instanceof Error ? exc.message : "No se pudo iniciar sesión.",
      );
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-3xl font-semibold tracking-tight text-brand-700">
            Credigest
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Gestión de préstamos para tu financiera
          </p>
        </div>

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="card space-y-4 p-6"
          noValidate
        >
          {serverError && <Alert tone="error">{serverError}</Alert>}

          <div>
            <label className="label" htmlFor="email">
              Correo electrónico
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              className="input"
              placeholder="admin@mifinanciera.mx"
              {...register("email")}
            />
            {errors.email && <p className="field-error">{errors.email.message}</p>}
          </div>

          <div>
            <label className="label" htmlFor="password">
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="input"
              placeholder="••••••••••"
              {...register("password")}
            />
            {errors.password && (
              <p className="field-error">{errors.password.message}</p>
            )}
          </div>

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Entrando…" : "Iniciar sesión"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-500">
          ¿Olvidaste tu contraseña? Pide a tu administrador que la restablezca.
        </p>
      </div>
    </div>
  );
}
