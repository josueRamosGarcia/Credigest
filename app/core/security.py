"""Utilidades de seguridad: hash de contrasenas.

La contrasena nunca se guarda en claro (RNF-06). Se usa bcrypt, que es lento a
proposito para encarecer los ataques por fuerza bruta.

Se usa la libreria `bcrypt` directamente en lugar de `passlib`: passlib 1.7.4
no es compatible con bcrypt 5.x y su ultima version es de 2020.
"""

import bcrypt

#: bcrypt solo considera los primeros 72 bytes; una contrasena mas larga se
#: rechaza para que el usuario no crea que el resto aporta seguridad.
MAX_PASSWORD_BYTES = 72

#: Coste de bcrypt. 12 tarda decenas de milisegundos: suficiente para que el
#: login sea rapido y un ataque por fuerza bruta sea caro.
BCRYPT_ROUNDS = 12

#: Longitud minima aceptada para una contrasena nueva.
MIN_PASSWORD_LENGTH = 10


class PasswordError(ValueError):
    """Error de validacion de contrasena."""


def _validate(password: str) -> bytes:
    """Valida la contrasena y la devuelve codificada en UTF-8.

    Raises:
        PasswordError: Si es demasiado corta o excede el limite de bcrypt.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(
            f"La contrasena debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )

    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordError(
            f"La contrasena no puede superar {MAX_PASSWORD_BYTES} bytes en UTF-8."
        )
    return encoded


def hash_password(password: str) -> str:
    """Convierte una contrasena en su hash bcrypt.

    Args:
        password: Contrasena en claro.

    Returns:
        El hash listo para guardarse en la base de datos.

    Raises:
        PasswordError: Si la contrasena no cumple las validaciones.
    """
    encoded = _validate(password)
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Comprueba si una contrasena corresponde a un hash.

    Args:
        password: Contrasena en claro que intenta el usuario.
        password_hash: Hash almacenado.

    Returns:
        `True` si coinciden, `False` en caso contrario.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False

    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash con formato invalido: se trata como credencial incorrecta y no
        # se revela el motivo real.
        return False
