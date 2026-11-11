/** Pruebas del cliente HTTP: tokens, errores y renovación. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, request, tokens } from "@/api/client";

/** Crea una respuesta falsa de `fetch`. */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("tokens", () => {
  beforeEach(() => localStorage.clear());

  it("guarda y lee los tokens", () => {
    tokens.save("acceso", "refresco");

    expect(tokens.access).toBe("acceso");
    expect(tokens.refresh).toBe("refresco");
  });

  it("limpia los tokens", () => {
    tokens.save("a", "b");
    tokens.clear();

    expect(tokens.access).toBeNull();
    expect(tokens.refresh).toBeNull();
  });
});

describe("request", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("envía el cuerpo como JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await request("/test", { method: "POST", body: { a: 1 } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"a":1}');
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("adjunta el token en la cabecera", async () => {
    tokens.save("mi-token", "refresco");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);

    await request("/test");

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer mi-token");
  });

  it("omite el token con skipAuth", async () => {
    tokens.save("mi-token", "refresco");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);

    await request("/login", { method: "POST", skipAuth: true });

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("devuelve undefined en 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    const result = await request("/test", { method: "DELETE" });

    expect(result).toBeUndefined();
  });

  it("lanza ApiError con el mensaje del backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "El cliente no existe." }, 404)),
    );

    await expect(request("/clients/1")).rejects.toThrow("El cliente no existe.");
  });

  it("marca el código de estado en ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "No permitido" }, 403)),
    );

    await expect(request("/test")).rejects.toMatchObject({ status: 403 });
  });

  it("traduce errores de validación al español", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ loc: ["body", "curp"], msg: "String should be 18 characters" }] },
          422,
        ),
      ),
    );

    await expect(request("/clients")).rejects.toThrow("curp:");
  });

  it("usa un mensaje genérico si no hay cuerpo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));

    await expect(request("/test")).rejects.toThrow("error en el servidor");
  });

  it("renueva el token al recibir 401 y reintenta", async () => {
    tokens.save("viejo", "refresco-valido");

    const fetchMock = vi
      .fn()
      // 1: la peticion original falla con 401
      .mockResolvedValueOnce(jsonResponse({ detail: "expirado" }, 401))
      // 2: el refresh responde bien
      .mockResolvedValueOnce(jsonResponse({ access_token: "nuevo", refresh_token: "r2" }))
      // 3: el reintento funciona
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    vi.stubGlobal("fetch", fetchMock);

    const result = await request("/test");

    expect(result).toEqual({ ok: true });
    expect(tokens.access).toBe("nuevo");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("emite evento cuando el refresh falla", async () => {
    tokens.save("viejo", "refresco-invalido");

    const listener = vi.fn();
    window.addEventListener("credigest:session-expired", listener);

    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ detail: "expirado" }, 401))
        .mockResolvedValueOnce(jsonResponse({ detail: "invalido" }, 401)),
    );

    await expect(request("/test")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledOnce();

    window.removeEventListener("credigest:session-expired", listener);
  });

  it("no reintenta si no hay refresh guardado", async () => {
    tokens.save("viejo", "");
    localStorage.removeItem("credigest.refresh_token");

    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "expirado" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    await expect(request("/test")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
