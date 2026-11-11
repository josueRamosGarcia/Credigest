/** Pruebas de los componentes de interfaz. */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  Alert,
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Spinner,
  StatCard,
} from "@/components/ui";

describe("StatCard", () => {
  it("muestra la etiqueta y el valor", () => {
    render(<StatCard label="Capital prestado" value="$16,000.00" />);

    expect(screen.getByText("Capital prestado")).toBeInTheDocument();
    expect(screen.getByText("$16,000.00")).toBeInTheDocument();
  });

  it("muestra la pista cuando se pasa", () => {
    render(<StatCard label="Cartera" value="$5,000.00" hint="4 préstamos" />);

    expect(screen.getByText("4 préstamos")).toBeInTheDocument();
  });

  it("omite la pista si no se pasa", () => {
    const { container } = render(<StatCard label="X" value="1" />);

    expect(container.querySelectorAll("p")).toHaveLength(2);
  });

  it("aplica el tono de alerta", () => {
    const { container } = render(<StatCard label="Vencida" value="100" tone="bad" />);

    expect(container.firstElementChild?.className).toContain("red");
  });
});

describe("Badge", () => {
  it("muestra el contenido", () => {
    render(<Badge>Activo</Badge>);
    expect(screen.getByText("Activo")).toBeInTheDocument();
  });

  it("acepta clases de color", () => {
    render(<Badge className="bg-green-100">Pagado</Badge>);

    expect(screen.getByText("Pagado").className).toContain("bg-green-100");
  });
});

describe("EmptyState", () => {
  it("muestra título y descripción", () => {
    render(<EmptyState title="Sin clientes" description="Registra el primero." />);

    expect(screen.getByText("Sin clientes")).toBeInTheDocument();
    expect(screen.getByText("Registra el primero.")).toBeInTheDocument();
  });

  it("muestra la acción cuando se pasa", () => {
    render(<EmptyState title="Vacío" action={<button>Crear</button>} />);

    expect(screen.getByRole("button", { name: "Crear" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("muestra el mensaje", () => {
    render(<ErrorState message="No se pudo cargar" />);
    expect(screen.getByText("No se pudo cargar")).toBeInTheDocument();
  });

  it("llama a onRetry al presionar el botón", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Error" onRetry={onRetry} />);

    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("no muestra botón sin onRetry", () => {
    render(<ErrorState message="Error" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("Alert", () => {
  it("muestra el mensaje", () => {
    render(<Alert tone="error">Algo falló</Alert>);
    expect(screen.getByText("Algo falló")).toBeInTheDocument();
  });

  it("usa el tono indicado", () => {
    render(<Alert tone="success">Guardado</Alert>);

    expect(screen.getByRole("alert").className).toContain("green");
  });

  it("por defecto es informativo", () => {
    render(<Alert>Nota</Alert>);
    expect(screen.getByRole("alert").className).toContain("blue");
  });
});

describe("Spinner", () => {
  it("muestra la etiqueta por defecto", () => {
    render(<Spinner />);
    expect(screen.getByText("Cargando…")).toBeInTheDocument();
  });

  it("acepta una etiqueta propia", () => {
    render(<Spinner label="Calculando…" />);
    expect(screen.getByText("Calculando…")).toBeInTheDocument();
  });
});

describe("Pagination", () => {
  it("no se muestra si no hay resultados", () => {
    const { container } = render(
      <Pagination page={1} pageSize={20} total={0} onChange={() => {}} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("muestra el total y la página", () => {
    render(<Pagination page={2} pageSize={20} total={45} onChange={() => {}} />);

    expect(screen.getByText("45 resultados")).toBeInTheDocument();
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("usa singular con un resultado", () => {
    render(<Pagination page={1} pageSize={20} total={1} onChange={() => {}} />);

    expect(screen.getByText("1 resultado")).toBeInTheDocument();
  });

  it("desactiva 'Anterior' en la primera página", () => {
    render(<Pagination page={1} pageSize={20} total={45} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
  });

  it("desactiva 'Siguiente' en la última página", () => {
    render(<Pagination page={3} pageSize={20} total={45} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  });

  it("avanza de página", async () => {
    const onChange = vi.fn();
    render(<Pagination page={1} pageSize={20} total={45} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("retrocede de página", async () => {
    const onChange = vi.fn();
    render(<Pagination page={2} pageSize={20} total={45} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Anterior" }));

    expect(onChange).toHaveBeenCalledWith(1);
  });
});

describe("PageHeader", () => {
  it("muestra el título y la descripción", () => {
    render(<PageHeader title="Clientes" description="Tus clientes" />);

    expect(screen.getByRole("heading", { name: "Clientes" })).toBeInTheDocument();
    expect(screen.getByText("Tus clientes")).toBeInTheDocument();
  });

  it("muestra las acciones", () => {
    render(<PageHeader title="X" actions={<button>Nuevo</button>} />);

    expect(screen.getByRole("button", { name: "Nuevo" })).toBeInTheDocument();
  });
});
