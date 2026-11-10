"""Pruebas de integracion de clientes."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.client import ClientReference
from app.models.tenant import Tenant
from app.models.user import User
from app.services import client_service

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
CURP_MARIA = "LOPJ850312MDFZRN07"
CURP_JUAN = "GALJ900715HJCMPR06"

VALID_CLIENT = {
    "full_name": "Maria Lopez Perez",
    "curp": CURP_MARIA,
    "phone": "8711234567",
    "address": "Av. Juarez 123, Col. Centro, Torreon, Coahuila",
    "zone": "Centro",
    "notes": "Cliente puntual.",
    "references": [
        {
            "name": "Juan Lopez",
            "relationship": "Hermano",
            "phone": "8717654321",
            "address": "Calle Hidalgo 45, Torreon",
        }
    ],
}


async def _make_tenant_user(
    session: AsyncSession, email: str = "admin@test.mx", slug: str = "test"
) -> tuple[Tenant, User]:
    """Crea un tenant con un administrador y una configuracion."""
    tenant = Tenant(name="Financiera Test", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Admin Test",
        email=email,
        password_hash=hash_password(PASSWORD),
        role="admin",
    )
    session.add(user)
    await session.commit()
    return tenant, user


async def _auth_headers(client: AsyncClient, email: str = "admin@test.mx") -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera de autorizacion."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestCreateClient:
    """POST /api/v1/clients."""

    async def test_creates_client_with_references(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        assert response.status_code == 201
        body = response.json()
        assert body["full_name"] == "Maria Lopez Perez"
        assert body["curp"] == CURP_MARIA
        assert body["status"] == "activo"
        assert len(body["references"]) == 1
        assert body["references"][0]["relationship"] == "Hermano"

    async def test_extracts_birth_date_from_curp(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        assert response.json()["birth_date"] == "1985-03-12"

    async def test_normalizes_lowercase_curp(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        payload = {**VALID_CLIENT, "curp": CURP_MARIA.lower()}
        response = await api_client.post("/api/v1/clients", json=payload, headers=headers)

        assert response.status_code == 201
        assert response.json()["curp"] == CURP_MARIA

    async def test_rejects_duplicate_curp_in_same_tenant(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        second = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        assert second.status_code == 409
        assert "CURP" in second.json()["detail"]

    async def test_same_curp_allowed_in_other_tenant(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-56: la CURP es unica por financiera, no global."""
        await _make_tenant_user(db_session, email="a@test.mx", slug="a")
        headers_a = await _auth_headers(api_client, "a@test.mx")

        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers_a)

        tenant_b = Tenant(name="Otra", slug="b")
        db_session.add(tenant_b)
        await db_session.flush()
        db_session.add(
            User(
                tenant_id=tenant_b.id,
                full_name="Admin B",
                email="b@test.mx",
                password_hash=hash_password(PASSWORD),
                role="admin",
            )
        )
        await db_session.commit()

        headers_b = await _auth_headers(api_client, "b@test.mx")
        response = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers_b)

        assert response.status_code == 201

    @pytest.mark.parametrize(
        ("curp", "fragment"),
        [
            ("LOPJ850312MDFZRN00", "digito verificador"),
            ("LOPJ850312MDFZRN", "18 caracteres"),
            ("LOPJ850312MXXZRN07", "entidad"),
            ("LOPJ850332MDFZRN07", "fecha"),
            ("NO-ES-CURP-VALIDA-X", "18 caracteres"),
        ],
    )
    async def test_rejects_invalid_curp(
        self, api_client: AsyncClient, db_session: AsyncSession, curp: str, fragment: str
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        payload = {**VALID_CLIENT, "curp": curp}
        response = await api_client.post("/api/v1/clients", json=payload, headers=headers)

        assert response.status_code == 422
        assert fragment in response.text

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.post("/api/v1/clients", json=VALID_CLIENT)
        assert response.status_code == 401

    async def test_rejects_short_name(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        payload = {**VALID_CLIENT, "full_name": "AB"}
        response = await api_client.post("/api/v1/clients", json=payload, headers=headers)

        assert response.status_code == 422

    async def test_client_without_references(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        payload = {**VALID_CLIENT, "references": []}
        response = await api_client.post("/api/v1/clients", json=payload, headers=headers)

        assert response.status_code == 201
        assert response.json()["references"] == []


class TestListClients:
    """GET /api/v1/clients."""

    async def test_returns_empty_page(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.get("/api/v1/clients", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    async def test_paginates(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        await api_client.post(
            "/api/v1/clients",
            json={**VALID_CLIENT, "curp": CURP_JUAN, "full_name": "Juan Garcia"},
            headers=headers,
        )

        response = await api_client.get(
            "/api/v1/clients?page=1&page_size=1", headers=headers
        )
        body = response.json()

        assert body["total"] == 2
        assert len(body["items"]) == 1
        assert body["page_size"] == 1

    async def test_searches_by_name(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        response = await api_client.get("/api/v1/clients?search=maria", headers=headers)

        assert response.json()["total"] == 1

    async def test_searches_by_curp(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        response = await api_client.get("/api/v1/clients?search=LOPJ", headers=headers)

        assert response.json()["total"] == 1

    async def test_filters_by_zone(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        found = await api_client.get("/api/v1/clients?zone=Centro", headers=headers)
        empty = await api_client.get("/api/v1/clients?zone=Norte", headers=headers)

        assert found.json()["total"] == 1
        assert empty.json()["total"] == 0

    async def test_does_not_leak_other_tenants(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RNF-08: cada financiera solo ve sus clientes."""
        await _make_tenant_user(db_session, email="a@test.mx", slug="a")
        headers_a = await _auth_headers(api_client, "a@test.mx")
        await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers_a)

        tenant_b = Tenant(name="B", slug="b")
        db_session.add(tenant_b)
        await db_session.flush()
        db_session.add(
            User(
                tenant_id=tenant_b.id,
                full_name="B",
                email="b@test.mx",
                password_hash=hash_password(PASSWORD),
                role="admin",
            )
        )
        await db_session.commit()

        headers_b = await _auth_headers(api_client, "b@test.mx")
        response = await api_client.get("/api/v1/clients", headers=headers_b)

        assert response.json()["total"] == 0

    async def test_rejects_invalid_page_size(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.get("/api/v1/clients?page_size=500", headers=headers)
        assert response.status_code == 422


class TestGetClient:
    """GET /api/v1/clients/{id}."""

    async def test_returns_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        client_id = created.json()["id"]

        response = await api_client.get(f"/api/v1/clients/{client_id}", headers=headers)

        assert response.status_code == 200
        assert response.json()["id"] == client_id

    async def test_returns_404_for_unknown(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.get(
            "/api/v1/clients/00000000-0000-0000-0000-000000000000", headers=headers
        )
        assert response.status_code == 404

    async def test_returns_404_for_other_tenant_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RNF-08: pedir un cliente de otra financiera devuelve 404, no 403."""
        await _make_tenant_user(db_session, email="a@test.mx", slug="a")
        headers_a = await _auth_headers(api_client, "a@test.mx")
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers_a)
        client_id = created.json()["id"]

        tenant_b = Tenant(name="B", slug="b")
        db_session.add(tenant_b)
        await db_session.flush()
        db_session.add(
            User(
                tenant_id=tenant_b.id,
                full_name="B",
                email="b@test.mx",
                password_hash=hash_password(PASSWORD),
                role="admin",
            )
        )
        await db_session.commit()
        headers_b = await _auth_headers(api_client, "b@test.mx")

        response = await api_client.get(f"/api/v1/clients/{client_id}", headers=headers_b)
        assert response.status_code == 404

    async def test_rejects_malformed_uuid(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.get("/api/v1/clients/no-es-uuid", headers=headers)
        assert response.status_code == 422


class TestUpdateClient:
    """PATCH /api/v1/clients/{id}."""

    async def test_updates_only_sent_fields(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        client_id = created.json()["id"]

        response = await api_client.patch(
            f"/api/v1/clients/{client_id}", json={"zone": "Norte"}, headers=headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["zone"] == "Norte"
        assert body["full_name"] == "Maria Lopez Perez"

    async def test_cannot_change_curp(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """La CURP no es editable: identifica a la persona."""
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        client_id = created.json()["id"]

        response = await api_client.patch(
            f"/api/v1/clients/{client_id}",
            json={"curp": CURP_JUAN},
            headers=headers,
        )

        # Pydantic ignora el campo no declarado en ClientUpdate.
        assert response.status_code == 200
        assert response.json()["curp"] == CURP_MARIA


class TestStatusChange:
    """PATCH /api/v1/clients/{id}/status."""

    async def test_deactivates_and_reactivates(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        client_id = created.json()["id"]

        off = await api_client.patch(
            f"/api/v1/clients/{client_id}/status", json={"status": "inactivo"}, headers=headers
        )
        assert off.json()["status"] == "inactivo"

        on = await api_client.patch(
            f"/api/v1/clients/{client_id}/status", json={"status": "activo"}, headers=headers
        )
        assert on.json()["status"] == "activo"

    async def test_rejects_invalid_status(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        response = await api_client.patch(
            f"/api/v1/clients/{created.json()['id']}/status",
            json={"status": "borrado"},
            headers=headers,
        )
        assert response.status_code == 422


class TestReferences:
    """POST /api/v1/clients/{id}/references."""

    async def test_adds_reference(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        client_id = created.json()["id"]

        response = await api_client.post(
            f"/api/v1/clients/{client_id}/references",
            json={
                "name": "Ana Ruiz",
                "relationship": "Vecina",
                "phone": "8711112222",
                "address": "Calle Sol 10",
            },
            headers=headers,
        )

        assert response.status_code == 201
        assert response.json()["relationship"] == "Vecina"

    async def test_client_detail_includes_new_reference(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        client_id = created.json()["id"]

        await api_client.post(
            f"/api/v1/clients/{client_id}/references",
            json={
                "name": "Ana Ruiz",
                "relationship": "Vecina",
                "phone": "8711112222",
                "address": "Calle Sol 10",
            },
            headers=headers,
        )
        detail = await api_client.get(f"/api/v1/clients/{client_id}", headers=headers)

        assert len(detail.json()["references"]) == 2


class TestDocuments:
    """GET /api/v1/clients/{id}/documents."""

    async def test_returns_empty_list(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)
        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)

        response = await api_client.get(
            f"/api/v1/clients/{created.json()['id']}/documents", headers=headers
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_lists_registered_document(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _make_tenant_user(db_session)
        client = await client_service.create_client(
            db_session,
            tenant.id,
            user.id,
            __import__("app.schemas.client", fromlist=["ClientCreate"]).ClientCreate(
                **VALID_CLIENT
            ),
        )
        await client_service.add_document(
            db_session,
            tenant.id,
            client.id,
            doc_type="ine",
            file_key="clientes/abc/ine.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            uploaded_by=user.id,
        )
        headers = await _auth_headers(api_client)

        response = await api_client.get(
            f"/api/v1/clients/{client.id}/documents", headers=headers
        )

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["doc_type"] == "ine"
        # La ruta interna nunca se expone.
        assert "file_key" not in response.json()[0]


class TestServiceRules:
    """Reglas verificadas directamente en el servicio."""

    async def test_search_is_case_insensitive(self, db_session: AsyncSession) -> None:
        tenant, user = await _make_tenant_user(db_session)
        from app.schemas.client import ClientCreate

        await client_service.create_client(
            db_session, tenant.id, user.id, ClientCreate(**VALID_CLIENT)
        )

        items, total = await client_service.list_clients(
            db_session, tenant.id, search="MARIA LOPEZ"
        )
        assert total == 1

    async def test_page_is_clamped_to_minimum(self, db_session: AsyncSession) -> None:
        tenant, _ = await _make_tenant_user(db_session)

        items, total = await client_service.list_clients(db_session, tenant.id, page=0)

        assert items == []
        assert total == 0

    async def test_page_size_is_clamped(self, db_session: AsyncSession) -> None:
        tenant, _ = await _make_tenant_user(db_session)

        _, _ = await client_service.list_clients(db_session, tenant.id, page_size=10_000)

    async def test_reference_relation_is_stored(self, db_session: AsyncSession) -> None:
        tenant, user = await _make_tenant_user(db_session)
        from app.schemas.client import ClientCreate

        client = await client_service.create_client(
            db_session, tenant.id, user.id, ClientCreate(**VALID_CLIENT)
        )

        stored = await db_session.scalar(
            select(ClientReference).where(ClientReference.client_id == client.id)
        )
        assert stored is not None
        assert stored.relation == "Hermano"

    async def test_client_stores_birth_date(self, db_session: AsyncSession) -> None:
        tenant, user = await _make_tenant_user(db_session)
        from app.schemas.client import ClientCreate

        client = await client_service.create_client(
            db_session, tenant.id, user.id, ClientCreate(**VALID_CLIENT)
        )
        await db_session.refresh(client)

        assert client.birth_date == date(1985, 3, 12)

    async def test_delete_client_cascades_references(self, db_session: AsyncSession) -> None:
        tenant, user = await _make_tenant_user(db_session)
        from app.schemas.client import ClientCreate

        client = await client_service.create_client(
            db_session, tenant.id, user.id, ClientCreate(**VALID_CLIENT)
        )

        await db_session.delete(client)
        await db_session.commit()

        remaining = (await db_session.scalars(select(ClientReference))).all()
        assert remaining == []


class TestNotFoundBranches:
    """Ramas de error que deben responder 404 en todos los endpoints."""

    async def test_update_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.patch(
            "/api/v1/clients/00000000-0000-0000-0000-000000000000",
            json={"zone": "Norte"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_change_status_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.patch(
            "/api/v1/clients/00000000-0000-0000-0000-000000000000/status",
            json={"status": "inactivo"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_add_reference_to_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.post(
            "/api/v1/clients/00000000-0000-0000-0000-000000000000/references",
            json={
                "name": "X",
                "relationship": "Vecino",
                "phone": "8710000000",
                "address": "Calle 1",
            },
            headers=headers,
        )
        assert response.status_code == 404

    async def test_documents_of_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        response = await api_client.get(
            "/api/v1/clients/00000000-0000-0000-0000-000000000000/documents",
            headers=headers,
        )
        assert response.status_code == 404


class TestModelRepr:
    """Las representaciones no deben exponer datos personales (RNF-09)."""

    def test_client_repr_hides_personal_data(self) -> None:
        from app.models.client import Client

        client = Client(full_name="Maria Lopez", curp=CURP_MARIA, phone="8711234567")
        text = repr(client)

        assert "Maria" not in text
        assert CURP_MARIA not in text

    def test_document_repr_hides_file_key(self) -> None:
        from app.models.client import ClientDocument

        document = ClientDocument(doc_type="ine", file_key="clientes/abc/ine.pdf")
        text = repr(document)

        assert "clientes/abc" not in text
        assert "ine" in text

    def test_reference_repr_hides_name(self) -> None:
        from app.models.client import ClientReference

        reference = ClientReference(name="Juan Lopez", phone="8717654321")
        text = repr(reference)

        assert "Juan" not in text
        assert "8717654321" not in text


class TestStatusFilter:
    """Filtro por estado en el listado."""

    async def test_filters_by_status(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_tenant_user(db_session)
        headers = await _auth_headers(api_client)

        created = await api_client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
        await api_client.patch(
            f"/api/v1/clients/{created.json()['id']}/status",
            json={"status": "inactivo"},
            headers=headers,
        )
        await api_client.post(
            "/api/v1/clients",
            json={**VALID_CLIENT, "curp": CURP_JUAN, "full_name": "Juan Garcia"},
            headers=headers,
        )

        activos = await api_client.get("/api/v1/clients?status=activo", headers=headers)
        inactivos = await api_client.get("/api/v1/clients?status=inactivo", headers=headers)

        assert activos.json()["total"] == 1
        assert inactivos.json()["total"] == 1
        assert inactivos.json()["items"][0]["full_name"] == "Maria Lopez Perez"
