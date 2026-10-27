"""Pruebas de las utilidades de seguridad."""

import pytest

from app.core.security import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    PasswordError,
    hash_password,
    verify_password,
)

VALID_PASSWORD = "clave-segura-123"


class TestHashPassword:
    """El hash debe ser bcrypt y no revelar la contrasena."""

    def test_returns_bcrypt_prefix(self) -> None:
        hashed = hash_password(VALID_PASSWORD)
        assert hashed.startswith("$2b$")

    def test_uses_cost_twelve(self) -> None:
        """El coste se codifica en el propio hash despues del prefijo."""
        hashed = hash_password(VALID_PASSWORD)
        assert hashed.split("$")[2] == "12"

    def test_does_not_contain_plain_password(self) -> None:
        hashed = hash_password(VALID_PASSWORD)
        assert VALID_PASSWORD not in hashed

    def test_two_hashes_of_same_password_differ(self) -> None:
        """Cada hash usa una sal aleatoria distinta."""
        first = hash_password(VALID_PASSWORD)
        second = hash_password(VALID_PASSWORD)

        assert first != second
        assert verify_password(VALID_PASSWORD, first)
        assert verify_password(VALID_PASSWORD, second)

    def test_rejects_short_password(self) -> None:
        with pytest.raises(PasswordError, match="al menos"):
            hash_password("corta")

    def test_accepts_exact_minimum_length(self) -> None:
        password = "a" * MIN_PASSWORD_LENGTH
        assert verify_password(password, hash_password(password))

    def test_rejects_password_over_72_bytes(self) -> None:
        with pytest.raises(PasswordError, match="72 bytes"):
            hash_password("a" * (MAX_PASSWORD_BYTES + 1))

    def test_accepts_exactly_72_bytes(self) -> None:
        password = "a" * MAX_PASSWORD_BYTES
        assert verify_password(password, hash_password(password))

    def test_counts_bytes_not_characters(self) -> None:
        """Una letra con acento ocupa 2 bytes en UTF-8."""
        password = "ñ" * 40  # 80 bytes
        with pytest.raises(PasswordError, match="72 bytes"):
            hash_password(password)


class TestVerifyPassword:
    """Verificacion de contrasenas."""

    def test_accepts_correct_password(self) -> None:
        hashed = hash_password(VALID_PASSWORD)
        assert verify_password(VALID_PASSWORD, hashed) is True

    def test_rejects_wrong_password(self) -> None:
        hashed = hash_password(VALID_PASSWORD)
        assert verify_password("otra-clave-distinta", hashed) is False

    def test_rejects_empty_password(self) -> None:
        hashed = hash_password(VALID_PASSWORD)
        assert verify_password("", hashed) is False

    def test_rejects_malformed_hash(self) -> None:
        assert verify_password(VALID_PASSWORD, "no-es-un-hash") is False

    def test_rejects_empty_hash(self) -> None:
        assert verify_password(VALID_PASSWORD, "") is False

    def test_rejects_overlong_attempt_without_raising(self) -> None:
        """Una contrasena demasiado larga devuelve False, no un error."""
        hashed = hash_password(VALID_PASSWORD)
        assert verify_password("a" * 200, hashed) is False

    def test_is_case_sensitive(self) -> None:
        hashed = hash_password(VALID_PASSWORD)
        assert verify_password(VALID_PASSWORD.upper(), hashed) is False
