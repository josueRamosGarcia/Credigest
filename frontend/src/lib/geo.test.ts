import { describe, expect, it } from "vitest";

import {
  buildGoogleMapsRouteUrl,
  buildGoogleMapsStopUrl,
  composeAddress,
  mergeZoneOptions,
  optimizeStopOrder,
  parseCoordinate,
} from "./geo";

describe("geo utilities", () => {
  it("compone la dirección estructurada de Torreón", () => {
    expect(
      composeAddress({
        street: "Calzada Colón",
        exterior_number: "450",
        neighborhood: "Centro",
        postal_code: "27000",
        city: "Torreón",
        state: "Coahuila",
      }),
    ).toBe("Calzada Colón 450, Col. Centro, C.P. 27000, Torreón, Coahuila");
  });

  it("combina zonas existentes y sugeridas sin duplicar por mayúsculas", () => {
    const zones = mergeZoneOptions(["centro", "Mi Colonia Nueva"]);
    expect(zones[0]).toBe("centro");
    expect(zones).toContain("Mi Colonia Nueva");
    expect(zones).toContain("Viñedos");
    expect(zones.filter((z) => z.toLowerCase() === "centro")).toHaveLength(1);
  });

  it("parsea coordenadas válidas e ignora vacías", () => {
    expect(parseCoordinate("25.542800")).toBe(25.5428);
    expect(parseCoordinate(-103.4068)).toBe(-103.4068);
    expect(parseCoordinate(null)).toBeNull();
    expect(parseCoordinate("")).toBeNull();
  });

  it("optimiza el orden de paradas por vecino más cercano", () => {
    const ordered = optimizeStopOrder([
      { id: "a", lat: 25.54, lng: -103.4 },
      { id: "far", lat: 25.6, lng: -103.32 },
      { id: "near", lat: 25.545, lng: -103.402 },
      { id: "no-coords", lat: null, lng: null },
    ]);
    expect(ordered).toEqual(["a", "near", "far", "no-coords"]);
  });

  it("arma enlaces de Google Maps con coordenadas y con respaldo de dirección", () => {
    const single = buildGoogleMapsStopUrl({
      lat: 25.5428,
      lng: -103.4068,
      address: "Av. Juárez 123",
    });
    expect(single).toContain("destination=25.5428%2C-103.4068");

    const multi = buildGoogleMapsRouteUrl([
      { lat: 25.54, lng: -103.4, address: "A" },
      { lat: 25.55, lng: -103.39, address: "B" },
      { lat: null, lng: null, address: "Col. Centro" },
    ]);
    expect(multi).toContain("waypoints=25.54%2C-103.4%7C25.55%2C-103.39");
    expect(multi).toContain("Col.+Centro");
  });
});
