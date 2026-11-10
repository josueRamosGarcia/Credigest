"""Motor de aplicacion de pagos.

Reparte un pago entre las cuotas pendientes en el orden estricto que exige
RN-29: primero mora, luego interes y al final capital, empezando por la cuota
mas antigua.

Este modulo es puro: recibe el estado de las cuotas y el monto, y devuelve como
se reparte. No conoce la base de datos ni FastAPI, lo que permite probar los
casos limite en milisegundos.

Reglas cubiertas:
- RN-29: orden de aplicacion mora -> interes -> capital, cuota mas antigua primero.
- RN-30: cada aplicacion se reporta por separado para guardarse en auditoria.
- RN-31: un pago puede cubrir varias cuotas.
- RN-35: un pago adelantado reduce cuotas futuras sin cambiar sus fechas.
- RN-21: la mora no genera interes sobre si misma.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.money import MoneyError, round_money, to_decimal


class Concept(StrEnum):
    """Conceptos a los que se puede aplicar un pago."""

    MORA = "mora"
    INTERES = "interes"
    CAPITAL = "capital"


@dataclass(frozen=True)
class InstallmentState:
    """Estado de una cuota para el reparto de un pago.

    Los montos pagados se llevan por concepto, no solo en total, para que el
    reparto sea exacto aunque la mora crezca despues.

    Attributes:
        number: Numero de cuota, empezando en 1.
        amount: Total esperado de la cuota (capital + interes), sin mora.
        principal_part: Porcion de capital de la cuota.
        interest_part: Porcion de interes de la cuota.
        late_fee: Mora devengada acumulada.
        paid_late_fee: Cuanto se ha pagado ya de mora.
        paid_interest: Cuanto se ha pagado ya de interes.
        paid_principal: Cuanto se ha pagado ya de capital.
    """

    number: int
    amount: Decimal
    principal_part: Decimal
    interest_part: Decimal
    late_fee: Decimal = Decimal("0.00")
    paid_late_fee: Decimal = Decimal("0.00")
    paid_interest: Decimal = Decimal("0.00")
    paid_principal: Decimal = Decimal("0.00")

    @property
    def paid_amount(self) -> Decimal:
        """Total ya aplicado a esta cuota."""
        return round_money(self.paid_late_fee + self.paid_interest + self.paid_principal)

    @property
    def pending_late_fee(self) -> Decimal:
        """Mora que sigue pendiente."""
        return round_money(max(Decimal("0.00"), self.late_fee - self.paid_late_fee))

    @property
    def pending_interest(self) -> Decimal:
        """Interes que sigue pendiente."""
        return round_money(max(Decimal("0.00"), self.interest_part - self.paid_interest))

    @property
    def pending_principal(self) -> Decimal:
        """Capital que sigue pendiente."""
        return round_money(max(Decimal("0.00"), self.principal_part - self.paid_principal))

    @property
    def pending_total(self) -> Decimal:
        """Todo lo que falta de esta cuota, incluida la mora."""
        return round_money(
            self.pending_late_fee + self.pending_interest + self.pending_principal
        )

    @property
    def is_paid(self) -> bool:
        """Indica si la cuota ya esta liquidada."""
        return self.pending_total == Decimal("0.00")

    @property
    def status_after_payment(self) -> str:
        """Estado que le corresponde segun lo pagado.

        Solo distingue entre pendiente, parcial y pagada; el paso a "vencida"
        depende de la fecha y lo resuelve el servicio.
        """
        if self.is_paid:
            return "pagada"
        if self.paid_amount > Decimal("0.00"):
            return "parcial"
        return "pendiente"


@dataclass(frozen=True)
class Application:
    """Una porcion del pago aplicada a un concepto de una cuota."""

    installment_number: int
    concept: Concept
    amount: Decimal


@dataclass(frozen=True)
class Allocation:
    """Resultado de repartir un pago.

    Attributes:
        applications: Desglose por cuota y concepto.
        applied: Total efectivamente aplicado.
        unapplied: Sobrante que no se pudo aplicar (no deberia ocurrir si el
            servicio valida antes el saldo total).
        new_states: Estado de cada cuota despues del pago, indexado por numero.
    """

    applications: list[Application]
    applied: Decimal
    unapplied: Decimal
    new_states: dict[int, InstallmentState]

    @property
    def covers_multiple_installments(self) -> bool:
        """Indica si el pago alcanzo mas de una cuota (RN-31)."""
        return len({application.installment_number for application in self.applications}) > 1


def total_pending(installments: list[InstallmentState]) -> Decimal:
    """Suma todo lo pendiente del prestamo, incluida la mora.

    Es el monto maximo que se puede aceptar en un pago (RN-24).
    """
    return round_money(sum((row.pending_total for row in installments), Decimal("0.00")))


def allocate_payment(
    installments: list[InstallmentState],
    amount: Decimal | int | str,
) -> Allocation:
    """Reparte un pago entre las cuotas pendientes (RN-29).

    Args:
        installments: Cuotas del prestamo, en cualquier orden.
        amount: Monto recibido. Debe ser mayor que cero.

    Returns:
        El desglose de la aplicacion y el estado resultante de cada cuota.

    Raises:
        MoneyError: Si el monto no es positivo, si es mayor que el saldo total
            o si alguna cuota tiene datos inconsistentes.
    """
    normalized = round_money(to_decimal(amount, "monto del pago"))
    if normalized <= 0:
        raise MoneyError("El monto del pago debe ser mayor que cero.")

    _validate_installments(installments)

    ordered = sorted(installments, key=lambda row: row.number)
    available = total_pending(ordered)

    if normalized > available:
        raise MoneyError(
            f"El monto excede el saldo pendiente del prestamo ({available:.2f})."
        )

    remaining = normalized
    applications: list[Application] = []

    # Estado mutable por cuota mientras se reparte.
    working: dict[int, dict[str, Decimal]] = {
        row.number: {
            "late_fee": row.paid_late_fee,
            "interest": row.paid_interest,
            "principal": row.paid_principal,
        }
        for row in ordered
    }
    by_number = {row.number: row for row in ordered}

    for row in ordered:
        if remaining == 0:
            break

        for concept, pending_attr, bucket in (
            (Concept.MORA, "pending_late_fee", "late_fee"),
            (Concept.INTERES, "pending_interest", "interest"),
            (Concept.CAPITAL, "pending_principal", "principal"),
        ):
            if remaining == 0:
                break

            pending = getattr(row, pending_attr)
            if pending == 0:
                continue

            take = min(remaining, pending)
            take = round_money(take)
            if take == 0:
                continue

            working[row.number][bucket] = round_money(working[row.number][bucket] + take)
            applications.append(
                Application(
                    installment_number=row.number,
                    concept=concept,
                    amount=take,
                )
            )
            remaining = round_money(remaining - take)

    new_states = {
        number: InstallmentState(
            number=by_number[number].number,
            amount=by_number[number].amount,
            principal_part=by_number[number].principal_part,
            interest_part=by_number[number].interest_part,
            late_fee=by_number[number].late_fee,
            paid_late_fee=values["late_fee"],
            paid_interest=values["interest"],
            paid_principal=values["principal"],
        )
        for number, values in working.items()
    }

    applied = round_money(normalized - remaining)

    return Allocation(
        applications=applications,
        applied=applied,
        unapplied=round_money(remaining),
        new_states=new_states,
    )


def _validate_installments(installments: list[InstallmentState]) -> None:
    """Comprueba que las cuotas tengan datos coherentes.

    Raises:
        MoneyError: Si hay numeros repetidos, montos negativos o una cuota cuyo
            capital e interes no suman su total.
    """
    seen: set[int] = set()

    for row in installments:
        if row.number in seen:
            raise MoneyError(f"La cuota {row.number} esta repetida.")
        seen.add(row.number)

        if row.number < 1:
            raise MoneyError("El numero de cuota debe ser mayor o igual a 1.")

        for field, value in (
            ("amount", row.amount),
            ("principal_part", row.principal_part),
            ("interest_part", row.interest_part),
            ("late_fee", row.late_fee),
            ("paid_late_fee", row.paid_late_fee),
            ("paid_interest", row.paid_interest),
            ("paid_principal", row.paid_principal),
        ):
            if value < 0:
                raise MoneyError(f"El campo '{field}' de la cuota {row.number} es negativo.")

        if round_money(row.principal_part + row.interest_part) != row.amount:
            raise MoneyError(
                f"La cuota {row.number} no cuadra: capital + interes debe ser su monto."
            )

        if row.paid_late_fee > row.late_fee:
            raise MoneyError(f"La cuota {row.number} tiene pagada mas mora de la devengada.")

        if row.paid_interest > row.interest_part:
            raise MoneyError(f"La cuota {row.number} tiene pagado mas interes del cobrado.")

        if row.paid_principal > row.principal_part:
            raise MoneyError(f"La cuota {row.number} tiene pagado mas capital del prestado.")


def late_fee_covered(allocation: Allocation) -> Decimal:
    """Suma de la mora cubierta por el pago.

    Util para el comprobante: el cliente ve cuanto de su dinero se fue a mora.
    """
    return round_money(
        sum(
            (
                application.amount
                for application in allocation.applications
                if application.concept is Concept.MORA
            ),
            Decimal("0.00"),
        )
    )


def breakdown_by_concept(allocation: Allocation) -> dict[Concept, Decimal]:
    """Total aplicado a cada concepto.

    Es lo que se muestra en el recibo y en el dashboard.
    """
    totals: dict[Concept, Decimal] = {concept: Decimal("0.00") for concept in Concept}

    for application in allocation.applications:
        totals[application.concept] = round_money(
            totals[application.concept] + application.amount
        )

    return totals
