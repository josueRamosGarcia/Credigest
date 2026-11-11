/**
 * Contexto de autenticación.
 *
 * Guarda el usuario en memoria y los tokens en localStorage. Al arrancar, si
 * hay token, se consulta `/auth/me` para restaurar la sesión.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "@/api/auth";
import { tokens } from "@/api/client";
import { AuthContext, type AuthState } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<authApi.CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async () => {
    if (!tokens.access) {
      setUser(null);
      return;
    }

    try {
      const profile = await authApi.me();
      setUser(profile);
    } catch {
      tokens.clear();
      setUser(null);
    }
  }, []);

  // Restaura la sesión al cargar la aplicación.
  useEffect(() => {
    let active = true;

    (async () => {
      try {
        if (tokens.access) {
          const profile = await authApi.me();
          if (active) setUser(profile);
        }
      } catch {
        tokens.clear();
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  // Si el cliente HTTP no pudo renovar el token, se cierra la sesión.
  useEffect(() => {
    const handler = () => {
      tokens.clear();
      setUser(null);
    };

    window.addEventListener("credigest:session-expired", handler);
    return () => window.removeEventListener("credigest:session-expired", handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    try {
      const pair = await authApi.login(email, password);
      tokens.save(pair.access_token, pair.refresh_token);

      const profile = await authApi.me();
      setUser(profile);
    } catch (exc) {
      const message =
        exc instanceof Error ? exc.message : "No se pudo iniciar sesión.";
      setError(message);
      throw exc;
    }
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokens.refresh;

    try {
      if (refresh) await authApi.logout(refresh);
    } catch {
      // Si el servidor no responde, igual se limpia la sesión local.
    } finally {
      tokens.clear();
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, loading, error, login, logout, refreshUser }),
    [user, loading, error, login, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
