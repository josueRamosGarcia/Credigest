"""Conversion de importes a texto en espanol.

Se usa en el pagare: la cantidad debe aparecer con letra, no solo con numero,
porque es lo que da certeza al documento legal en Mexico.
"""

from decimal import Decimal

from app.domain.money import round_money, to_decimal

UNITS = (
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
)

TENS = {
    30: "treinta",
    40: "cuarenta",
    50: "cincuenta",
    60: "sesenta",
    70: "setenta",
    80: "ochenta",
    90: "noventa",
}

HUNDREDS = {
    100: "cien",
    200: "doscientos",
    300: "trescientos",
    400: "cuatrocientos",
    500: "quinientos",
    600: "seiscientos",
    700: "setecientos",
    800: "ochocientos",
    900: "novecientos",
}


def _hundreds_to_words(value: int) -> str:
    """Convierte un numero de 1 a 999 a palabras."""
    if value == 0:
        return ""

    if value <= 29:
        return UNITS[value]

    if value < 100:
        tens = (value // 10) * 10
        remainder = value % 10
        if remainder == 0:
            return TENS[tens]
        return f"{TENS[tens]} y {UNITS[remainder]}"

    if value == 100:
        return "cien"

    hundreds = (value // 100) * 100
    remainder = value % 100
    # "cien" solo se usa cuando es exactamente 100; con resto es "ciento".
    prefix = "ciento" if hundreds == 100 else HUNDREDS[hundreds]

    if remainder == 0:
        return prefix
    return f"{prefix} {_hundreds_to_words(remainder)}"


def _thousands_to_words(value: int) -> str:
    """Convierte un numero de 0 a 999,999 a palabras."""
    if value == 0:
        return "cero"

    if value < 1000:
        return _hundreds_to_words(value)

    thousands = value // 1000
    remainder = value % 1000

    prefix = "mil" if thousands == 1 else f"{_hundreds_to_words(thousands)} mil"

    if remainder == 0:
        return prefix
    return f"{prefix} {_hundreds_to_words(remainder)}"


def _millions_to_words(value: int) -> str:
    """Convierte un numero de 0 a 999,999,999 a palabras."""
    if value < 1_000_000:
        return _thousands_to_words(value)

    millions = value // 1_000_000
    remainder = value % 1_000_000

    prefix = "un millón" if millions == 1 else f"{_thousands_to_words(millions)} millones"

    if remainder == 0:
        return prefix
    return f"{prefix} {_thousands_to_words(remainder)}"


def amount_to_words(value: Decimal | int | str) -> str:
    """Convierte un importe a texto con centavos.

    Args:
        value: Importe monetario.

    Returns:
        El importe en letras, con la parte de centavos cuando exista.

    Example:
        >>> amount_to_words("16000.50")
        'dieciséis mil pesos 50/100 M.N.'
    """
    amount = round_money(to_decimal(value, "importe"))
    negative = amount < 0
    amount = abs(amount)

    integer_part = int(amount)
    cents = int((amount - integer_part) * 100)

    words = _millions_to_words(integer_part)
    unit = "peso" if integer_part == 1 else "pesos"
    result = f"{words} {unit}"

    if cents > 0:
        result = f"{result} {cents:02d}/100"

    result = f"{result} M.N."
    return f"menos {result}" if negative else result
