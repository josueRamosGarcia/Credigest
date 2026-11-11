/** Pantalla inicial de cada rol. */

/** Devuelve la ruta de inicio según el rol del usuario. */
export function homeFor(role: string): string {
  if (role === "admin") return "/dashboard";
  if (role === "prestamista") return "/clientes";
  return "/rutas";
}
