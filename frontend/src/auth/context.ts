/** Contexto de autenticación, separado del proveedor por Fast Refresh. */

import { createContext } from "react";

import type { CurrentUser } from "@/api/auth";

export interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Vuelve a cargar el perfil; útil si cambian los permisos. */
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);
