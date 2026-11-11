/**
 * Cliente HTTP de la API de Credigest.
 *
 * Dos decisiones importantes:
 *
 * 1. **Los montos viajan como texto**, no como número. El backend los envía
 *    como "1333.33" para no perder precisión al pasar por JavaScript, que usa
 *    coma flotante. Aquí se usan tal cual para mostrar y se convierten a
 *    número solo al enviar, donde el backend los vuelve a validar.
 *
 * 2. **El token de acceso se renueva solo.** Si una petición responde 401, se
 *    intenta un refresh una vez y se reintenta. Si el refresh falla, se cierra
 *    la sesión y se manda al login.
 */

const BASE_URL = "/api/v1";

const ACCESS_TOKEN_KEY = "credigest.access_token";
const REFRESH_TOKEN_KEY = "credigest.refresh_token";

/** Error de la API con el mensaje ya listo para mostrar al usuario. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Respuesta del backend cuando algo falla. */
interface ErrorBody {
  detail?: string | Array<{ msg?: string; loc?: (string | number)[] }>;
}

export const tokens = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  save(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

/**
 * Convierte el cuerpo de error del backend en un mensaje legible.
 *
 * FastAPI responde con `detail` como texto para errores de negocio y como una
 * lista de validación para errores de esquema.
 */
function extractMessage(body: ErrorBody, status: number): string {
  if (typeof body.detail === "string") {
    return body.detail;
  }

  if (Array.isArray(body.detail) && body.detail.length > 0) {
    const first = body.detail[0];
    const field = first.loc?.filter((part) => part !== "body").join(".");
    const message = first.msg ?? "Dato inválido";
    return field ? `${field}: ${message}` : message;
  }

  if (status === 401) return "Tu sesión expiró. Vuelve a iniciar sesión.";
  if (status === 403) return "No tienes permiso para esta acción.";
  if (status === 404) return "No se encontró el recurso.";
  if (status === 429) return "Demasiados intentos. Espera un momento.";
  if (status >= 500) return "Ocurrió un error en el servidor.";

  return "No se pudo completar la operación.";
}

/** Intenta renovar el par de tokens. Devuelve `false` si no fue posible. */
async function refreshTokens(): Promise<boolean> {
  const refresh = tokens.refresh;
  if (!refresh) return false;

  try {
    const response = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });

    if (!response.ok) return false;

    const data = (await response.json()) as {
      access_token: string;
      refresh_token: string;
    };
    tokens.save(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Evita el intento de refresh: útil en el propio login y refresh. */
  skipAuth?: boolean;
  signal?: AbortSignal;
}

/**
 * Hace una petición a la API y devuelve el JSON ya tipado.
 *
 * @throws {ApiError} Si la respuesta no es exitosa.
 */
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, skipAuth = false, signal } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const access = tokens.access;
  if (access && !skipAuth) headers.Authorization = `Bearer ${access}`;

  const send = () =>
    fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });

  let response = await send();

  // 401 con token: puede ser expiración. Se renueva una sola vez.
  if (response.status === 401 && access && !skipAuth) {
    const renewed = await refreshTokens();
    if (renewed) {
      headers.Authorization = `Bearer ${tokens.access}`;
      response = await send();
    } else {
      tokens.clear();
      window.dispatchEvent(new Event("credigest:session-expired"));
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let payload: ErrorBody = {};
    try {
      payload = (await response.json()) as ErrorBody;
    } catch {
      // Respuesta sin cuerpo: se usa el mensaje genérico por código.
    }
    throw new ApiError(response.status, extractMessage(payload, response.status), payload.detail);
  }

  return (await response.json()) as T;
}

/** Descarga un archivo binario (el pagaré) respetando el refresh de token. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const access = tokens.access;
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: access ? { Authorization: `Bearer ${access}` } : {},
  });

  if (!response.ok) {
    throw new ApiError(response.status, "No se pudo descargar el documento.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
