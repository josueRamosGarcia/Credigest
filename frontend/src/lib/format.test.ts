/** Pruebas de las utilidades de formato. */

import { describe, expect, it } from "vitest";

import {
  addDays,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatMoney,
  formatRate,
  initials,
  percentToRate,
  todayIso,
} from "@/lib/format";

describe("formatMoney", () => {
  it("agrupa miles y conserva dos decimales", () => {
    expect(formatMoney("1333.33")).toBe("1,333.33");
    expect(formatMoney("16000.00")).toBe("16,000.00");
    expect(formatMoney("1000000.50")).toBe("1,000,000.50");
  });

  it("rellena los decimales cuando faltan", () => {
    expect(formatMoney("1000")).toBe("1,000.00");
    expect(formatMoney("1000.5")).toBe("1,000.50");
  });

  it("maneja negativos", () => {
    expect(formatMoney("-1500.25")).toBe("-1,500.25");
  });

  it("devuelve guion para valores vacíos", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney("")).toBe("—");
  });

  it("no pierde dígitos con importes grandes", () => {
    // Un float perdería precisión aquí; el formateo a mano no.
    expect(formatMoney("9007199254740993.99")).toBe("9,007,199,254,740,993.99");
  });

  it("acepta números", () => {
    expect(formatMoney(1234.5)).toBe("1,234.50");
  });
});

describe("formatCurrency", () => {
  it("antepone el símbolo de peso", () => {
    expect(formatCurrency("1333.33")).toBe("$1,333.33");
  });

  it("respeta el guion", () => {
    expect(formatCurrency(null)).toBe("—");
  });
});

describe("formatRate", () => {
  it("convierte fracción a porcentaje", () => {
    expect(formatRate("0.05")).toBe("5 %");
    expect(formatRate("0.0525")).toBe("5.25 %");
    expect(formatRate("0.1")).toBe("10 %");
  });

  it("maneja cero", () => {
    expect(formatRate("0")).toBe("0 %");
  });

  it("devuelve guion para valores vacíos", () => {
    expect(formatRate(null)).toBe("—");
  });
});

describe("formatDate", () => {
  it("pasa de ISO a dd/mm/aaaa", () => {
    expect(formatDate("2026-11-02")).toBe("02/11/2026");
  });

  it("acepta fecha con hora", () => {
    expect(formatDate("2026-11-02T15:30:00Z")).toBe("02/11/2026");
  });

  it("devuelve guion si falta", () => {
    expect(formatDate(null)).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("incluye la hora local", () => {
    const result = formatDateTime("2026-11-02T15:30:00");
    expect(result).toBe("02/11/2026 15:30");
  });

  it("devuelve guion si falta", () => {
    expect(formatDateTime(undefined)).toBe("—");
  });

  it("devuelve el valor original si no es fecha", () => {
    expect(formatDateTime("no-es-fecha")).toBe("no-es-fecha");
  });
});

describe("todayIso", () => {
  it("devuelve el formato esperado", () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("addDays", () => {
  it("suma días", () => {
    expect(addDays("2026-11-01", 5)).toBe("2026-11-06");
  });

  it("cruza el fin de mes", () => {
    expect(addDays("2026-11-28", 5)).toBe("2026-12-03");
  });

  it("acepta días negativos", () => {
    expect(addDays("2026-11-10", -10)).toBe("2026-10-31");
  });
});

describe("percentToRate", () => {
  it("convierte porcentaje a fracción con cuatro decimales", () => {
    expect(percentToRate(5)).toBe("0.0500");
    expect(percentToRate("5.25")).toBe("0.0525");
  });
});

describe("initials", () => {
  it("toma las dos primeras iniciales", () => {
    expect(initials("María López Pérez")).toBe("ML");
  });

  it("funciona con un solo nombre", () => {
    expect(initials("Ana")).toBe("A");
  });

  it("devuelve cadena vacía sin nombre", () => {
    expect(initials("")).toBe("");
  });
});
