"""Pruebas unitarias para correcciones de seguridad (auditoria, IP y bcrypt)."""

from unittest.mock import MagicMock

import bcrypt
import pytest
from fastapi import HTTPException

from app.api.v1.audit import _safe_csv_cell
from app.core.deps import AuthContext, require_role
from app.core.request_meta import parse_ip, request_meta
from app.core.security import DUMMY_PASSWORD_HASH, verify_password
from app.models.tenant import Tenant
from app.models.user import User


class TestDummyBcryptHash:
    """El hash dummy debe ser valido para bcrypt (no lanzar ValueError)."""

    def test_dummy_hash_is_valid_bcrypt(self) -> None:
        # Si el salt fuera invalido, bcrypt.checkpw lanzaria ValueError.
        assert bcrypt.checkpw(b"cualquier-clave", DUMMY_PASSWORD_HASH.encode("utf-8")) is False

    def test_verify_password_uses_dummy_without_error(self) -> None:
        assert verify_password("clave-incorrecta", DUMMY_PASSWORD_HASH) is False


class TestRequestMetaIpValidation:
    """Solo se aceptan IPs validas para evitar DataError en columna INET."""

    def test_accepts_ipv4_and_ipv6(self) -> None:
        assert parse_ip("203.0.113.5") == "203.0.113.5"
        assert parse_ip("2001:db8::1") == "2001:db8::1"

    def test_rejects_malformed_ip_and_port(self) -> None:
        assert parse_ip("not-an-ip") is None
        assert parse_ip("1.2.3.4:5678") is None
        assert parse_ip("testclient") is None
        assert parse_ip("") is None

    def test_invalid_forwarded_falls_back_to_valid_client_host(self) -> None:
        request = MagicMock()
        request.headers = {
            "x-forwarded-for": "basura-inyectada, 10.0.0.1",
            "user-agent": "Mozilla/5.0",
        }
        request.client.host = "127.0.0.1"

        meta = request_meta(request)
        assert meta.ip_address == "127.0.0.1"

    def test_invalid_forwarded_and_invalid_client_returns_none(self) -> None:
        request = MagicMock()
        request.headers = {"x-forwarded-for": "basura"}
        request.client.host = "testclient"

        meta = request_meta(request)
        assert meta.ip_address is None


class TestAuditCsvSafetyAndAdminRole:
    """Neutralizacion de formulas CSV y restriccion de rol en auditoria."""

    def test_prefixes_formula_cells(self) -> None:
        assert _safe_csv_cell("=CMD|'/C calc'!A0") == "'=CMD|'/C calc'!A0"
        assert _safe_csv_cell("+1+1") == "'+1+1"
        assert _safe_csv_cell("-1+1") == "'-1+1"
        assert _safe_csv_cell("@SUM(A1)") == "'@SUM(A1)"
        assert _safe_csv_cell("client.create") == "client.create"
        assert _safe_csv_cell(None) is None

    async def test_audit_admin_dependency_blocks_non_admin(self) -> None:
        checker = require_role("admin")
        for role in ("cobrador", "prestamista"):
            ctx = AuthContext(user=User(role=role), tenant=Tenant(name="T"))
            with pytest.raises(HTTPException) as exc:
                await checker(ctx)
            assert exc.value.status_code == 403
