"""Reglas de dinero.

Credigest trabaja con `Decimal` para todos los importes (RN-01). Nunca se usa
`float` porque no puede representar exactamente valores como 0.10 y acumula
errores al sumar.

Referencias de las reglas de negocio:
- RN-01: los importes se representan con Decimal, no con float.
- RN-02: el redondeo es ROUND_HALF_UP a 2 decimales.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: Precision de los importes monetarios: 2 decimales.
CENTS = Decimal("0.01")

#: Numero de decimales usados por las tasas (4 permiten 0.0525).
RATE_EXPONENT = Decimal("0.0001")


class MoneyError(ValueError):
    """Error de negocio relacionado con importes o tasas."""


def to_decimal(value: Decimal | int | str, field: str = "importe") -> Decimal:
    """Convierte un valor a Decimal rechazando tipos inexactos.

    Acepta `Decimal`, `int` y `str`. Rechaza `float` de forma explicita para
    que un error de redondeo no pase inadvertido al resto del sistema.

    Args:
        value: Valor a convertir.
        field: Nombre del campo, usado en el mensaje de error.

    Returns:
        El valor convertido a Decimal.

    Raises:
        MoneyError: Si el valor es float, booleano o no se puede convertir.
    """
    if isinstance(value, bool):
        raise MoneyError(f"El campo '{field}' no puede ser un booleano.")
    if isinstance(value, float):
        raise MoneyError(
            f"El campo '{field}' no puede ser float: usa Decimal, int o str "
            "para evitar errores de redondeo."
        )
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MoneyError(f"El campo '{field}' no es un numero valido: {value!r}.") from exc


def round_money(value: Decimal) -> Decimal:
    """Redondea un importe a 2 decimales con ROUND_HALF_UP (RN-02).

    `ROUND_HALF_UP` redondea 0.005 hacia arriba, que es el criterio comercial
    habitual en Mexico. Python usa por defecto ROUND_HALF_EVEN, que redondearia
    0.005 hacia abajo y sorprenderia al usuario.
    """
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def round_rate(value: Decimal) -> Decimal:
    """Redondea una tasa a 4 decimales con ROUND_HALF_UP."""
    return value.quantize(RATE_EXPONENT, rounding=ROUND_HALF_UP)


def money(
    value: Decimal | int | str,
    field: str = "importe",
) -> Decimal:
    """Convierte y redondea un importe en un solo paso."""
    return round_money(to_decimal(value, field))


def rate(
    value: Decimal | int | str,
    field: str = "tasa",
) -> Decimal:
    """Convierte y redondea una tasa en un solo paso."""
    return round_rate(to_decimal(value, field))


def require_positive_amount(value: Decimal, field: str = "importe") -> Decimal:
    """Valida que un importe sea estrictamente mayor que cero (RN-10)."""
    if value <= 0:
        raise MoneyError(f"El campo '{field}' debe ser mayor que cero.")
    return value


def require_non_negative_rate(value: Decimal, field: str = "tasa") -> Decimal:
    """Valida que una tasa no sea negativa (RN-11)."""
    if value < 0:
        raise MoneyError(f"El campo '{field}' no puede ser negativo.")
    return value
