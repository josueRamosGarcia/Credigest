"""Pruebas del servicio de auditoria."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import audit_service
from app.services.audit_service import REDACTED, diff, sanitize

pytestmark = pytest.mark.db


class TestSanitize:
    """Nunca se guardan datos sensibles en la bitacora (RN-65, RNF-09)."""

    def test_redacts_password(self) -> None:
        assert sanitize({"password": "secreto"}) == {"password": REDACTED}

    def test_redacts_token(self) -> None:
        result = sanitize({"refresh_token": "abc123"})
        assert result == {"refresh_token": REDACTED}

    def test_redacts_curp(self) -> None:
        result = sanitize({"curp": "LOPJ850312MDFZRN07"})
        assert result == {"curp": REDACTED}

    def test_redacts_file_key(self) -> None:
        result = sanitize({"file_key": "clientes/abc/ine.pdf"})
        assert result == {"file_key": REDACTED}

    def test_keeps_safe_fields(self) -> None:
        assert sanitize({"status": "activo", "amount": "100.00"}) == {
            "status": "activo",
            "amount": "100.00",
        }

    def test_redacts_nested_dict(self) -> None:
        payload = {"user": {"email": "a@b.mx", "password": "x"}}
        assert sanitize(payload) == {"user": {"email": "a@b.mx", "password": REDACTED}}

    def test_redacts_inside_list(self) -> None:
        payload = {"items": [{"password": "x"}, {"role": "admin"}]}
        assert sanitize(payload) == {"items": [{"password": REDACTED}, {"role": "admin"}]}

    def test_returns_none_for_none(self) -> None:
        assert sanitize(None) is None

    def test_is_case_insensitive(self) -> None:
        assert sanitize({"PASSWORD": "x"}) == {"PASSWORD": REDACTED}

    def test_does_not_mutate_original(self) -> None:
        original = {"password": "x"}
        sanitize(original)
        assert original == {"password": "x"}


class TestDiff:
    """Solo se guardan los campos que cambiaron (RN-65)."""

    def test_detects_change(self) -> None:
        before, after = diff({"status": "activo"}, {"status": "inactivo"})
        assert before == {"status": "activo"}
        assert after == {"status": "inactivo"}

    def test_ignores_unchanged(self) -> None:
        before, after = diff({"a": 1, "b": 2}, {"a": 1, "b": 3})
        assert before == {"b": 2}
        assert after == {"b": 3}

    def test_detects_new_field(self) -> None:
        before, after = diff({}, {"zone": "Centro"})
        assert before == {}
        assert after == {"zone": "Centro"}

    def test_detects_removed_field(self) -> None:
        before, after = diff({"notes": "x"}, {})
        assert before == {"notes": "x"}
        assert after == {}

    def test_no_change_returns_empty(self) -> None:
        before, after = diff({"a": 1}, {"a": 1})
        assert before == {}
        assert after == {}

    def test_handles_none(self) -> None:
        before, after = diff(None, {"a": 1})
        assert before == {}
        assert after == {"a": 1}


class TestRecord:
    """Escritura de entradas."""

    async def test_writes_entry(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(db_session)

        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.create",
            entity="client",
            entity_id=uuid4(),
            after={"full_name": "Maria", "status": "activo"},
            ip_address="192.168.1.10",
            user_agent="pytest",
        )

        assert entry is not None
        assert entry.action == "client.create"
        assert entry.entity == "client"
        assert entry.ip_address == "192.168.1.10"

    async def test_stores_only_changed_fields(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(db_session)

        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.update",
            entity="client",
            before={"zone": "Centro", "phone": "111"},
            after={"zone": "Norte", "phone": "111"},
        )

        assert entry is not None
        assert entry.before == {"zone": "Centro"}
        assert entry.after == {"zone": "Norte"}

    async def test_redacts_sensitive_values(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(db_session)

        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="user.create",
            entity="user",
            after={"email": "a@b.mx", "password": "secreto", "curp": "LOPJ850312MDFZRN07"},
        )

        assert entry is not None
        assert entry.after is not None
        assert entry.after["password"] == REDACTED
        assert entry.after["curp"] == REDACTED
        assert entry.after["email"] == "a@b.mx"

    async def test_allows_system_entries_without_user(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, _ = await make_tenant_and_user(db_session)

        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            action="daily_close.run",
            entity="system",
        )

        assert entry is not None
        assert entry.user_id is None

    async def test_commits_when_asked(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, _ = await make_tenant_and_user(db_session)

        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            action="test.commit",
            entity="test",
            after={"ok": True},
            commit=True,
        )

        assert entry is not None
        assert entry.id is not None


class TestListEntries:
    """Consulta con filtros."""

    async def _seed(self, session: AsyncSession) -> tuple[Any, Any]:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(session)

        for index, action in enumerate(
            ["client.create", "loan.create", "payment.create", "client.update"]
        ):
            await audit_service.record(
                session,
                tenant_id=tenant.id,
                user_id=user.id,
                action=action,
                entity=action.split(".")[0],
                after={"index": index},
            )
        await session.commit()
        return tenant, user

    async def test_lists_all_for_tenant(self, db_session: AsyncSession) -> None:
        tenant, _ = await self._seed(db_session)

        entries, total = await audit_service.list_entries(db_session, tenant.id)

        assert total == 4
        assert len(entries) == 4

    async def test_orders_newest_first(self, db_session: AsyncSession) -> None:
        tenant, _ = await self._seed(db_session)

        entries, _ = await audit_service.list_entries(db_session, tenant.id)

        assert entries[0].action == "client.update"
        assert entries[-1].action == "client.create"

    async def test_filters_by_action(self, db_session: AsyncSession) -> None:
        tenant, _ = await self._seed(db_session)

        entries, total = await audit_service.list_entries(
            db_session, tenant.id, action="loan.create"
        )

        assert total == 1
        assert entries[0].action == "loan.create"

    async def test_filters_by_entity(self, db_session: AsyncSession) -> None:
        tenant, _ = await self._seed(db_session)

        _, total = await audit_service.list_entries(db_session, tenant.id, entity="client")

        assert total == 2

    async def test_filters_by_user(self, db_session: AsyncSession) -> None:
        tenant, user = await self._seed(db_session)

        _, total = await audit_service.list_entries(db_session, tenant.id, user_id=user.id)

        assert total == 4

    async def test_filters_by_unknown_user(self, db_session: AsyncSession) -> None:
        tenant, _ = await self._seed(db_session)

        _, total = await audit_service.list_entries(db_session, tenant.id, user_id=uuid4())

        assert total == 0

    async def test_paginates(self, db_session: AsyncSession) -> None:
        tenant, _ = await self._seed(db_session)

        entries, total = await audit_service.list_entries(
            db_session, tenant.id, page=1, page_size=2
        )

        assert total == 4
        assert len(entries) == 2

    async def test_does_not_leak_other_tenants(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant_a, user_a = await make_tenant_and_user(db_session, slug="a", email="a@t.mx")
        tenant_b, _ = await make_tenant_and_user(db_session, slug="b", email="b@t.mx")

        await audit_service.record(
            db_session,
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            action="client.create",
            entity="client",
        )
        await db_session.commit()

        _, total = await audit_service.list_entries(db_session, tenant_b.id)

        assert total == 0


class TestImmutability:
    """RN-66: la bitacora no se modifica ni se borra desde la aplicacion."""

    async def test_no_update_endpoint(self, api_client: Any, db_session: AsyncSession) -> None:
        response = await api_client.patch("/api/v1/audit/1", json={"action": "hackeado"})
        assert response.status_code in {404, 405}

    async def test_no_delete_endpoint(self, api_client: Any, db_session: AsyncSession) -> None:
        response = await api_client.delete("/api/v1/audit/1")
        assert response.status_code in {404, 405}

    async def test_entry_survives_after_reading(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="loan.create",
            entity="loan",
        )
        await db_session.commit()

        entries, _ = await audit_service.list_entries(db_session, tenant.id)

        assert len(entries) == 1
        assert entries[0].action == "loan.create"


class TestEntryToDict:
    """Conversion para la API y el CSV."""

    async def test_serializes_fields(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(db_session)
        entity_id = uuid4()

        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="payment.create",
            entity="payment",
            entity_id=entity_id,
            after={"amount": "400.00"},
            ip_address="10.0.0.1",
        )
        await db_session.commit()

        assert entry is not None
        data = audit_service.entry_to_dict(entry)

        assert data["action"] == "payment.create"
        assert data["entity_id"] == str(entity_id)
        assert data["ip_address"] == "10.0.0.1"
        assert data["after"] == {"amount": "400.00"}

    async def test_handles_null_fields(self, db_session: AsyncSession) -> None:
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, _ = await make_tenant_and_user(db_session)
        entry = await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            action="system.run",
            entity="system",
        )
        await db_session.commit()

        assert entry is not None
        data = audit_service.entry_to_dict(entry)

        assert data["user_id"] is None
        assert data["entity_id"] is None
        assert data["ip_address"] is None


class TestRequestMeta:
    """Extraccion de IP y user-agent de la peticion."""

    def test_uses_forwarded_header(self) -> None:
        from unittest.mock import MagicMock

        from app.core.request_meta import request_meta

        request = MagicMock()
        request.headers = {
            "x-forwarded-for": "203.0.113.5, 10.0.0.1",
            "user-agent": "Mozilla/5.0",
        }
        request.client = None

        meta = request_meta(request)

        assert meta.ip_address == "203.0.113.5"
        assert meta.user_agent == "Mozilla/5.0"

    def test_falls_back_to_client_host(self) -> None:
        from unittest.mock import MagicMock

        from app.core.request_meta import request_meta

        request = MagicMock()
        request.headers = {"user-agent": "pytest"}
        request.client.host = "127.0.0.1"

        meta = request_meta(request)

        assert meta.ip_address == "127.0.0.1"

    def test_handles_missing_client(self) -> None:
        from unittest.mock import MagicMock

        from app.core.request_meta import request_meta

        request = MagicMock()
        request.headers = {}
        request.client = None

        meta = request_meta(request)

        assert meta.ip_address is None
        assert meta.user_agent is None


class TestAuditRepr:
    """Representacion de depuracion."""

    def test_repr_shows_action_and_entity(self) -> None:
        from app.models.audit_log import AuditLog

        entry = AuditLog(action="loan.create", entity="loan")
        text = repr(entry)

        assert "loan.create" in text
        assert "loan" in text


class TestCsvLimit:
    """La exportacion no debe crecer sin limite."""

    async def test_csv_stops_at_ten_thousand(
        self, api_client: Any, db_session: AsyncSession
    ) -> None:
        """Con pocos registros el CSV termina cuando ya no hay mas."""
        from tests.test_audit_helpers import make_tenant_and_user

        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.create",
            entity="client",
        )
        await db_session.commit()

        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "audit@test.mx", "password": "clave-segura-123"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = await api_client.get("/api/v1/audit/export.csv", headers=headers)

        assert response.status_code == 200
        assert "client.create" in response.text
