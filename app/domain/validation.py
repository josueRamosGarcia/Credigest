"""Validacion de la CURP mexicana.

La CURP (Clave Unica de Registro de Poblacion) tiene 18 caracteres con una
estructura fija. Validarla antes de guardar evita datos basura y errores al
generar el pagare.

Estructura (RN-55)::

    LOPJ 850312 M DF ZRN 0 5
    │    │      │ │  │   │ └─ digito verificador
    │    │      │ │  │   └─── homoclave (0-9 para 1900s, A-Z para 2000s)
    │    │      │ │  └─────── consonantes internas (3)
    │    │      │ └────────── entidad federativa (2)
    │    │      └──────────── sexo: H, M o X
    │    └─────────────────── fecha de nacimiento AAMMDD
    └──────────────────────── iniciales (4)

Este modulo es puro: no conoce base de datos ni FastAPI.
"""

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

#: Alfabeto usado por el digito verificador. Notese la Ñ en su posicion.
_ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"

#: Entidades federativas validas, incluida NE (nacido en el extranjero).
STATE_CODES = frozenset(
    {
        "AS",  # Aguascalientes
        "BC",  # Baja California
        "BS",  # Baja California Sur
        "CC",  # Campeche
        "CL",  # Coahuila
        "CM",  # Colima
        "CS",  # Chiapas
        "CH",  # Chihuahua
        "DF",  # Ciudad de Mexico
        "DG",  # Durango
        "GT",  # Guanajuato
        "GR",  # Guerrero
        "HG",  # Hidalgo
        "JC",  # Jalisco
        "MC",  # Estado de Mexico
        "MN",  # Michoacan
        "MS",  # Morelos
        "NT",  # Nayarit
        "NL",  # Nuevo Leon
        "OC",  # Oaxaca
        "PL",  # Puebla
        "QT",  # Queretaro
        "QR",  # Quintana Roo
        "SP",  # San Luis Potosi
        "SL",  # Sinaloa
        "SR",  # Sonora
        "TC",  # Tabasco
        "TS",  # Tamaulipas
        "TL",  # Tlaxcala
        "VZ",  # Veracruz
        "YN",  # Yucatan
        "ZS",  # Zacatecas
        "NE",  # Nacido en el extranjero
    }
)

#: Patron estructural: 4 letras, 6 digitos, sexo, entidad, 3 consonantes,
#: homoclave y digito verificador.
_CURP_PATTERN = re.compile(
    r"^[A-ZÑ]{4}\d{6}[HMX][A-Z]{2}[B-DF-HJ-NP-TV-ZÑ]{3}[0-9A-Z]\d$"
)


class CurpError(ValueError):
    """La CURP no cumple la estructura o el digito verificador."""


class Sex(StrEnum):
    """Sexo registrado en la CURP."""

    HOMBRE = "H"
    MUJER = "M"
    NO_BINARIO = "X"


@dataclass(frozen=True)
class CurpData:
    """Datos extraidos de una CURP valida."""

    curp: str
    birth_date: date
    sex: Sex
    state: str


def normalize_curp(value: str) -> str:
    """Normaliza una CURP a mayusculas y sin separadores (RN-55).

    Args:
        value: La CURP tal como la escribio el usuario.

    Returns:
        La CURP en mayusculas, sin espacios ni guiones.

    Raises:
        CurpError: Si el valor esta vacio o no es texto.
    """
    if not isinstance(value, str):
        raise CurpError("La CURP debe ser texto.")
    cleaned = value.strip().upper().replace(" ", "").replace("-", "")
    if not cleaned:
        raise CurpError("La CURP no puede estar vacia.")
    return cleaned


def curp_check_digit(first_seventeen: str) -> str:
    """Calcula el digito verificador de los primeros 17 caracteres.

    Algoritmo oficial del RENAPO: cada caracter toma su valor en el alfabeto y
    se multiplica por un peso descendente de 17 a 1.

    Args:
        first_seventeen: Los primeros 17 caracteres de la CURP.

    Returns:
        El digito verificador como texto.

    Raises:
        CurpError: Si la cadena no tiene 17 caracteres o contiene un simbolo
            fuera del alfabeto.
    """
    if len(first_seventeen) != 17:
        raise CurpError("Se requieren exactamente 17 caracteres para el digito verificador.")

    total = 0
    for position, char in enumerate(first_seventeen, start=1):
        try:
            value = _ALPHABET.index(char)
        except ValueError as exc:
            raise CurpError(f"Caracter no valido en la CURP: {char!r}.") from exc
        total += value * (18 - position)

    return str((10 - (total % 10)) % 10)


def _birth_date(curp: str) -> date:
    """Extrae y valida la fecha de nacimiento.

    El siglo se deduce de la homoclave (posicion 17): un digito indica 1900s y
    una letra indica 2000s. Esa es la regla oficial.
    """
    year, month, day = int(curp[4:6]), int(curp[6:8]), int(curp[8:10])
    century = 1900 if curp[16].isdigit() else 2000

    try:
        return date(century + year, month, day)
    except ValueError as exc:
        raise CurpError("La fecha de nacimiento de la CURP no existe.") from exc


def parse_curp(value: str) -> CurpData:
    """Valida una CURP y devuelve sus datos.

    Args:
        value: La CURP a validar.

    Returns:
        Los datos extraidos: CURP normalizada, fecha, sexo y entidad.

    Raises:
        CurpError: Si la estructura, la entidad, la fecha o el digito
            verificador no son correctos.
    """
    curp = normalize_curp(value)

    if len(curp) != 18:
        raise CurpError(f"La CURP debe tener 18 caracteres, se recibieron {len(curp)}.")

    if not _CURP_PATTERN.match(curp):
        raise CurpError("La CURP no tiene la estructura esperada.")

    state = curp[11:13]
    if state not in STATE_CODES:
        raise CurpError(f"La entidad '{state}' no es una clave valida de la CURP.")

    birth_date = _birth_date(curp)

    expected = curp_check_digit(curp[:17])
    if curp[17] != expected:
        raise CurpError("El digito verificador de la CURP no es correcto.")

    return CurpData(
        curp=curp,
        birth_date=birth_date,
        sex=Sex(curp[10]),
        state=state,
    )


def is_valid_curp(value: str) -> bool:
    """Indica si una CURP es valida, sin lanzar excepciones."""
    try:
        parse_curp(value)
    except CurpError:
        return False
    return True
