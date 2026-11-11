/**
 * Utilidades de formato.
 *
 * Importante: los montos llegan como texto ("1333.33"). Aquí solo se formatean
 * para mostrarlos; nunca se convierten a `number` para volver a enviarlos, para
 * no perder precisión.
 */

/** Formatea un importe como moneda mexicana: "1,333.33". */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";

  const raw = typeof value === "number" ? value.toFixed(2) : value;

  // Se formatea a mano en lugar de usar Intl para no perder dígitos con
  // importes grandes: Intl trabaja con number y eso reintroduce el redondeo.
  const [integerPart, decimals = "00"] = raw.split(".");
  const negative = integerPart.startsWith("-");
  const digits = negative ? integerPart.slice(1) : integerPart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  return `${negative ? "-" : ""}${grouped}.${decimals.padEnd(2, "0").slice(0, 2)}`;
}

/** Formatea un importe con el símbolo de peso: "$1,333.33". */
export function formatCurrency(value: string | number | null | undefined): string {
  const formatted = formatMoney(value);
  return formatted === "—" ? formatted : `$${formatted}`;
}

/** Convierte una tasa en fracción ("0.0500") a porcentaje legible: "5 %". */
export function formatRate(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";

  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) return "—";

  const percent = numeric * 100;
  const text = percent.toFixed(2).replace(/\.?0+$/, "");
  return `${text} %`;
}

/** Formatea una fecha ISO (YYYY-MM-DD) como dd/mm/aaaa. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";

  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;

  return `${day}/${month}/${year}`;
}

/** Formatea una fecha y hora ISO como dd/mm/aaaa hh:mm. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${day}/${month}/${date.getFullYear()} ${hours}:${minutes}`;
}

/** Devuelve la fecha de hoy en formato ISO, en hora local. */
export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** Suma días a una fecha ISO y devuelve otra fecha ISO. */
export function addDays(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T12:00:00`);
  date.setDate(date.getDate() + days);

  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Convierte un porcentaje capturado ("5") a la fracción que espera la API ("0.05"). */
export function percentToRate(percent: string | number): string {
  const value = typeof percent === "number" ? percent : Number(percent);
  if (Number.isNaN(value)) return "0";
  return (value / 100).toFixed(4);
}

/** Devuelve las iniciales de un nombre para el avatar. */
export function initials(fullName: string): string {
  return fullName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
