"""Pruebas de validacion de CURP (RN-55)."""

from datetime import date

import pytest

from app.domain.validation import (
    CurpError,
    Sex,
    curp_check_digit,
    is_valid_curp,
    normalize_curp,
    parse_curp,
)

#: CURP validas generadas con el algoritmo oficial del RENAPO.
VALID_1985 = "LOPJ850312MDFZRN07"
VALID_1990 = "GALJ900715HJCMPR06"


class TestNormalize:
    """La CURP se normaliza antes de validar."""

    def test_uppercases(self) -> None:
        assert normalize_curp(VALID_1985.lower()) == VALID_1985

    def test_removes_spaces(self) -> None:
        assert normalize_curp(" LOPJ850312MDFZRN07 ") == VALID_1985

    def test_removes_hyphens(self) -> None:
        assert normalize_curp("LOPJ-850312-MDFZRN-07") == VALID_1985

    def test_rejects_empty(self) -> None:
        with pytest.raises(CurpError, match="vacia"):
            normalize_curp("   ")

    def test_rejects_non_string(self) -> None:
        with pytest.raises(CurpError, match="texto"):
            normalize_curp(12345)  # type: ignore[arg-type]


class TestCheckDigit:
    """Algoritmo del digito verificador."""

    def test_known_curp_1985(self) -> None:
        assert curp_check_digit(VALID_1985[:17]) == "7"

    def test_known_curp_1990(self) -> None:
        assert curp_check_digit(VALID_1990[:17]) == "6"

    def test_requires_seventeen_chars(self) -> None:
        with pytest.raises(CurpError, match="17 caracteres"):
            curp_check_digit("LOPJ850312")

    def test_rejects_symbol_outside_alphabet(self) -> None:
        with pytest.raises(CurpError, match="no valido"):
            curp_check_digit("LOPJ850312MDFZRN@")


class TestParse:
    """Extraccion de datos de una CURP valida."""

    def test_parses_valid_curp(self) -> None:
        data = parse_curp(VALID_1985)

        assert data.curp == VALID_1985
        assert data.birth_date == date(1985, 3, 12)
        assert data.sex is Sex.MUJER
        assert data.state == "DF"

    def test_parses_male(self) -> None:
        data = parse_curp(VALID_1990)
        assert data.sex is Sex.HOMBRE
        assert data.birth_date == date(1990, 7, 15)

    def test_century_is_derived_from_homoclave(self) -> None:
        """Homoclave con digito = 1900s; con letra = 2000s."""
        assert parse_curp(VALID_1985).birth_date.year == 1985

    def test_accepts_lowercase(self) -> None:
        assert parse_curp(VALID_1985.lower()).curp == VALID_1985


class TestParseRejects:
    """Casos que deben rechazarse con mensaje claro."""

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            ("", "vacia"),
            ("LOPJ8503", "18 caracteres"),
            (VALID_1985 + "X", "18 caracteres"),
            ("LOPJ850312MDFZRN0X", "estructura"),
            ("LOPJ850312ZDFZRN07", "estructura"),
            ("LOPJ850312MXXZRN07", "entidad"),
            ("LOPJ850332MDFZRN07", "fecha"),
            ("LOPJ851332MDFZRN07", "fecha"),
        ],
    )
    def test_rejects_invalid(self, value: str, message: str) -> None:
        with pytest.raises(CurpError, match=message):
            parse_curp(value)

    def test_rejects_wrong_check_digit(self) -> None:
        wrong = VALID_1985[:17] + ("0" if VALID_1985[17] != "0" else "1")
        with pytest.raises(CurpError, match="digito verificador"):
            parse_curp(wrong)

    def test_rejects_impossible_day(self) -> None:
        """31 de febrero no existe."""
        with pytest.raises(CurpError, match="fecha"):
            parse_curp("LOPJ850231MDFZRN07")

    def test_rejects_invalid_month(self) -> None:
        with pytest.raises(CurpError, match="fecha"):
            parse_curp("LOPJ851312MDFZRN07")


class TestIsValid:
    """Version booleana, comoda para validadores."""

    def test_true_for_valid(self) -> None:
        assert is_valid_curp(VALID_1985) is True

    def test_false_for_invalid(self) -> None:
        assert is_valid_curp("no-es-curp") is False

    def test_false_for_empty(self) -> None:
        assert is_valid_curp("") is False


class TestStateCodes:
    """Todas las entidades declaradas deben ser aceptadas por el patron."""

    def test_all_states_are_two_uppercase_letters(self) -> None:
        from app.domain.validation import STATE_CODES

        assert len(STATE_CODES) == 33
        assert all(len(code) == 2 and code.isalpha() for code in STATE_CODES)

    def test_foreign_born_state_is_accepted(self) -> None:
        """NE significa nacido en el extranjero."""
        from app.domain.validation import STATE_CODES

        assert "NE" in STATE_CODES
