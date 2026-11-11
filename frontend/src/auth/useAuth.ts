/** Hooks de autenticación. */

import { useContext } from "react";

import type { CurrentUser } from "@/api/auth";
import { AuthContext, type AuthState } from "./context";

/** Accede al contexto de autenticación. */
export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth debe usarse dentro de <AuthProvider>.");
  }
  return context;
}

/** Indica si el usuario tiene uno de los roles indicados. */
export function hasRole(
  user: CurrentUser | null,
  ...roles: string[]
): boolean {
  if (!user) return false;
  if (user.role === "admin") return true;
  return roles.includes(user.role);
}
