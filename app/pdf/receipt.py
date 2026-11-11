"""Generacion del comprobante de pago en PDF.

Formato angosto (80 mm) para que quepa en una impresora de tickets o se pueda
enviar como imagen por WhatsApp.
"""

import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.money import round_money
from app.models.client import Client
from app.models.loan import Loan
from app.models.payment import Payment
from app.models.tenant import Tenant
from app.models.user import User
from app.pdf.amount_words import amount_to_words
from app.pdf.generator import (
    MissingDependencyError,
    PdfError,
    _environment,
    _format_money,
)


def local_date_of(payment: Payment) -> date:
    """Fecha del pago en la zona del negocio.

    `created_at` se guarda en UTC: sin convertir, un cobro de las 20:00 en
    Mexico apareceria con la fecha del dia siguiente.
    """
    from zoneinfo import ZoneInfo

    from app.core.config import get_settings

    return payment.created_at.astimezone(ZoneInfo(get_settings().timezone)).date()


#: Etiquetas de las formas de pago.
METHOD_LABELS = {
    "efectivo": "Efectivo",
    "spei": "Transferencia SPEI",
}

#: Etiquetas de los conceptos.
CONCEPT_LABELS = {
    "mora": "Mora",
    "interes": "Interés",
    "capital": "Capital",
}

#: Etiquetas del estado del prestamo.
LOAN_STATUS_LABELS = {
    "activo": "Activo",
    "pagado": "Pagado",
    "vencido": "Vencido",
    "cancelado": "Cancelado",
}


@dataclass(frozen=True)
class ReceiptContext:
    """Datos que consume la plantilla del comprobante."""

    tenant: dict[str, Any]
    client: dict[str, Any]
    payment: dict[str, Any]
    loan: dict[str, Any]
    concepts: list[dict[str, str]]


def build_receipt_context(
    *,
    tenant: Tenant,
    client: Client,
    loan: Loan,
    payment: Payment,
    applications: list[tuple[str, Decimal]],
    remaining_total: Decimal,
    registered_by: User | None = None,
    issued_date: date | None = None,
) -> ReceiptContext:
    """Arma los datos del comprobante.

    Args:
        tenant: Financiera que emite.
        client: Cliente que pago.
        loan: Prestamo al que se abono.
        payment: Pago registrado.
        applications: Lista de (concepto, monto) del pago.
        remaining_total: Saldo pendiente del prestamo despues del pago.
        registered_by: Usuario que registro el cobro.
        issued_date: Fecha del comprobante.

    Returns:
        El contexto listo para renderizar.
    """
    moment = issued_date or local_date_of(payment)

    # Se agrupan las aplicaciones por concepto para mostrarlas en una sola linea.
    grouped: dict[str, Decimal] = {}
    for concept, amount in applications:
        grouped[concept] = round_money(grouped.get(concept, Decimal("0.00")) + amount)

    concepts = [
        {
            "label": CONCEPT_LABELS.get(concept, concept),
            "amount": _format_money(amount),
        }
        for concept, amount in grouped.items()
        if amount > 0
    ]

    if not concepts:
        concepts = [
            {"label": CONCEPT_LABELS["capital"], "amount": _format_money(payment.amount)}
        ]

    return ReceiptContext(
        tenant={"name": tenant.name},
        client={
            "full_name": client.full_name,
            "curp": client.curp,
        },
        payment={
            "folio": payment.folio,
            "date": moment.strftime("%d/%m/%Y"),
            "amount": _format_money(payment.amount),
            "amount_words": amount_to_words(payment.amount),
            "method_label": METHOD_LABELS.get(payment.method, payment.method),
            "spei_reference": payment.spei_reference,
            "status": payment.status,
            "cancel_reason": payment.cancel_reason,
            "registered_by": registered_by.full_name if registered_by else "Sistema",
        },
        loan={
            "remaining_total": _format_money(remaining_total),
            "status_label": LOAN_STATUS_LABELS.get(loan.status, loan.status),
        },
        concepts=concepts,
    )


def render_receipt_html(context: ReceiptContext) -> str:
    """Renderiza la plantilla del comprobante a HTML."""
    template = _environment().get_template("comprobante.html")
    return template.render(
        tenant=context.tenant,
        client=context.client,
        payment=context.payment,
        loan=context.loan,
        concepts=context.concepts,
    )


def render_receipt_pdf(context: ReceiptContext) -> bytes:
    """Genera el PDF del comprobante.

    Raises:
        MissingDependencyError: Si WeasyPrint no esta disponible.
        PdfError: Si falla la conversion.
    """
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - depende del sistema
        raise MissingDependencyError(
            "WeasyPrint no esta instalado. Ejecuta las instrucciones del README."
        ) from exc
    except OSError as exc:  # pragma: no cover - depende del sistema
        raise MissingDependencyError(
            "Faltan librerias del sistema para WeasyPrint."
        ) from exc

    html = render_receipt_html(context)

    try:
        buffer = io.BytesIO()
        HTML(string=html).write_pdf(buffer)
        return buffer.getvalue()
    except Exception as exc:  # pragma: no cover - depende del sistema
        raise PdfError(f"No se pudo generar el comprobante: {exc}") from exc


def receipt_filename(payment: Payment) -> str:
    """Nombre de archivo sugerido para el comprobante."""
    return f"{payment.folio.lower()}.pdf"


def whatsapp_link(phone: str, *, tenant_name: str, payment: Payment) -> str:
    """Arma un enlace de WhatsApp con el resumen del pago.

    Usa el esquema `wa.me`, que abre la aplicacion sin necesitar la API de
    WhatsApp ni credenciales.

    Args:
        phone: Telefono del cliente. Se limpian los caracteres no numericos y se
            antepone el codigo de pais si falta.
        tenant_name: Nombre de la financiera.
        payment: Pago registrado.

    Returns:
        La URL lista para abrir en el navegador o compartir.
    """
    digits = "".join(character for character in phone if character.isdigit())

    # Mexico: 52 + 10 digitos. Si ya viene con 52, se respeta.
    if len(digits) == 10:
        digits = f"52{digits}"
    elif digits.startswith("52") and len(digits) == 12:
        pass

    message = (
        f"*{tenant_name}* — Comprobante de pago\n"
        f"Folio: {payment.folio}\n"
        f"Monto: ${_format_money(payment.amount)}\n"
        f"Fecha: {local_date_of(payment).strftime('%d/%m/%Y')}\n\n"
        "Gracias por su pago."
    )

    from urllib.parse import quote

    return f"https://wa.me/{digits}?text={quote(message)}"
