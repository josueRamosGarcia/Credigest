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

/** Promesa compartida para deduplicar renovaciones concurrentes de token. */
let refreshInFlight: Promise<boolean> | null = null;

/** Intenta renovar el par de tokens. Devuelve `false` si no fue posible. */
async function performRefresh(): Promise<boolean> {
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

/** Renueva tokens reutilizando la peticion en vuelo si ya hay una activa. */
async function refreshTokens(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * Ejecuta `fetch` contra la API adjuntando el token y renovando una vez ante 401.
 * Sirve tanto para JSON como para descargas binarias y subidas `FormData`.
 */
export async function authorizedFetch(
  path: string,
  init: RequestInit & { skipAuth?: boolean } = {},
): Promise<Response> {
  const { skipAuth = false, headers: rawHeaders, ...rest } = init;
  const headers: Record<string, string> = {};

  if (rawHeaders instanceof Headers) {
    rawHeaders.forEach((value, key) => {
      headers[key] = value;
    });
  } else if (Array.isArray(rawHeaders)) {
    for (const [key, value] of rawHeaders) {
      headers[key] = value;
    }
  } else if (rawHeaders) {
    Object.assign(headers, rawHeaders);
  }

  const access = tokens.access;
  if (access && !skipAuth) headers.Authorization = `Bearer ${access}`;

  const send = () => fetch(`${BASE_URL}${path}`, { ...rest, headers });

  let response = await send();

  // 401 con token: puede ser expiracion. Se renueva una sola vez (deduplicado).
  if (response.status === 401 && access && !skipAuth) {
    const renewed = await refreshTokens();
    if (renewed && tokens.access) {
      headers.Authorization = `Bearer ${tokens.access}`;
      response = await send();
    } else {
      tokens.clear();
      window.dispatchEvent(new Event("credigest:session-expired"));
    }
  }

  return response;
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

  const response = await authorizedFetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    skipAuth,
    signal,
  });

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

/** Descarga un archivo binario (pagaré, recibo, CSV) respetando el refresh de token. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await authorizedFetch(path);

  if (!response.ok) {
    let payload: ErrorBody = {};
    try {
      payload = (await response.json()) as ErrorBody;
    } catch {
      // Sin cuerpo JSON: se usa el mensaje generico.
    }
    throw new ApiError(
      response.status,
      typeof payload.detail === "string"
        ? payload.detail
        : "No se pudo descargar el documento.",
      payload.detail,
    );
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
