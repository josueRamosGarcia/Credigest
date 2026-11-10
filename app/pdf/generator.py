"""Generacion del pagare en PDF.

Convierte una plantilla HTML con los datos del prestamo en un PDF listo para
imprimir. La logica de calculo ya esta resuelta: aqui solo se presentan los
datos.

Si WeasyPrint no esta instalado (faltan las librerias del sistema), la excepcion
se propaga con un mensaje claro en lugar de fallar de forma confusa.
"""

import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.domain.amortization import build_schedule, schedule_totals
from app.domain.interest import Frequency, LoanTerms, Scheme
from app.domain.money import round_money
from app.models.client import Client
from app.models.loan import Loan
from app.models.tenant import Tenant
from app.pdf.amount_words import amount_to_words

#: Ruta de las plantillas HTML.
TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Etiquetas legibles de las frecuencias de pago.
FREQUENCY_LABELS = {
    "semanal": "semanal",
    "quincenal": "quincenal",
    "mensual": "mensual",
}

#: Etiquetas legibles de los esquemas de calculo.
SCHEME_LABELS = {
    "simple": "Interés simple sobre capital original",
    "saldo_insoluto": "Interés sobre saldo insoluto",
    "cuota_fija": "Cuota fija precalculada",
}


class PdfError(RuntimeError):
    """No se pudo generar el documento."""


class MissingDependencyError(PdfError):
    """WeasyPrint no esta disponible en el sistema."""


@dataclass(frozen=True)
class PagareContext:
    """Datos que consume la plantilla del pagare."""

    tenant: dict[str, Any]
    client: dict[str, Any]
    loan: dict[str, Any]
    installments: list[dict[str, Any]]
    totals: dict[str, str]
    issued_date: str


def _environment() -> Environment:
    """Crea el entorno de Jinja2 con autoescape activado."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _format_money(value: Decimal) -> str:
    """Formatea un importe con separador de miles y dos decimales."""
    rounded = round_money(value)
    return f"{rounded:,.2f}"


def _format_percent(value: Decimal) -> str:
    """Convierte una fraccion a porcentaje legible."""
    percent = (value * 100).normalize()
    text = f"{percent:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def build_context(
    *,
    tenant: Tenant,
    client: Client,
    loan: Loan,
    issued_date: date | None = None,
) -> PagareContext:
    """Arma los datos que necesita la plantilla.

    El calendario se recalcula desde las condiciones congeladas del prestamo, que
    son inmutables. Asi el PDF siempre refleja lo que se firmo.

    Args:
        tenant: Financiera que emite el documento.
        client: Deudor.
        loan: Prestamo aprobado.
        issued_date: Fecha de emision; por defecto hoy.

    Returns:
        El contexto listo para renderizar.
    """
    terms = LoanTerms.create(
        principal=loan.principal,
        rate=loan.interest_rate,
        periods=loan.term_periods,
        frequency=Frequency(loan.rate_period),
        scheme=Scheme(loan.scheme),
    )

    schedule = build_schedule(terms, loan.start_date)
    total_amount, total_interest, total_principal = schedule_totals(schedule)

    rows = [
        {
            "number": row.number,
            "due_date": row.due_date.strftime("%d/%m/%Y"),
            "amount": _format_money(row.amount),
            "interest_part": _format_money(row.interest_part),
            "principal_part": _format_money(row.principal_part),
            "balance": _format_money(row.balance),
        }
        for row in schedule
    ]

    frequency = loan.rate_period
    folio = f"PAG-{(tenant.slug or 'CRD').upper()}-{loan.id.hex[:8].upper()}"

    return PagareContext(
        tenant={
            "name": tenant.name,
            "slug": tenant.slug,
        },
        client={
            "full_name": client.full_name,
            "curp": client.curp,
            "phone": client.phone,
            "address": client.address,
        },
        loan={
            "folio": folio,
            "principal": _format_money(loan.principal),
            "total_amount": _format_money(total_amount),
            "total_amount_words": amount_to_words(total_amount),
            "total_interest": _format_money(total_interest),
            "interest_rate_percent": _format_percent(loan.interest_rate),
            "rate_period_label": FREQUENCY_LABELS.get(frequency, frequency),
            "installment_label": "pagos",
            "scheme_label": SCHEME_LABELS.get(loan.scheme, loan.scheme),
            "term_periods": loan.term_periods,
            "start_date": loan.start_date.strftime("%d/%m/%Y"),
            "first_due_date": loan.first_due_date.strftime("%d/%m/%Y"),
            "end_date": loan.end_date.strftime("%d/%m/%Y"),
            "late_fee_rate_percent": _format_percent(loan.late_fee_rate),
            "grace_days": loan.grace_days,
        },
        installments=rows,
        totals={
            "amount": _format_money(total_amount),
            "interest": _format_money(total_interest),
            "principal": _format_money(total_principal),
        },
        issued_date=(issued_date or date.today()).strftime("%d/%m/%Y"),
    )


def render_pagare_html(context: PagareContext) -> str:
    """Renderiza la plantilla del pagare a HTML.

    Se expone por separado para poder probar el contenido sin WeasyPrint.
    """
    template = _environment().get_template("pagare.html")
    return template.render(
        tenant=context.tenant,
        client=context.client,
        loan=context.loan,
        installments=context.installments,
        totals=context.totals,
        issued_date=context.issued_date,
    )


def render_pagare_pdf(context: PagareContext) -> bytes:
    """Genera el PDF del pagare.

    Args:
        context: Datos ya preparados.

    Returns:
        Los bytes del PDF.

    Raises:
        MissingDependencyError: Si WeasyPrint o sus librerias no estan
            disponibles.
        PdfError: Si falla la conversion.
    """
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - depende del sistema
        raise MissingDependencyError(
            "WeasyPrint no esta instalado. En Ubuntu/WSL ejecuta: "
            "sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 "
            "libgdk-pixbuf-2.0-0 fonts-dejavu-core"
        ) from exc
    except OSError as exc:  # pragma: no cover - depende del sistema
        raise MissingDependencyError(
            "Faltan librerias del sistema para WeasyPrint. Ejecuta: "
            "sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 "
            "libgdk-pixbuf-2.0-0 fonts-dejavu-core"
        ) from exc

    html = render_pagare_html(context)

    try:
        buffer = io.BytesIO()
        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(buffer)
        return buffer.getvalue()
    except Exception as exc:  # pragma: no cover - depende del sistema
        raise PdfError(f"No se pudo generar el PDF: {exc}") from exc


def pagare_filename(tenant: Tenant, loan: Loan) -> str:
    """Nombre de archivo sugerido para la descarga."""
    label = (tenant.slug or "credigest").lower()
    return f"pagare-{label}-{loan.id.hex[:8]}.pdf"
