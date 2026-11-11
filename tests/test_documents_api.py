"""Pruebas de subida, descarga y borrado de documentos."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import reset_storage
from app.models.audit_log import AuditLog
from app.models.client import ClientDocument
from tests.test_audit_helpers import PASSWORD, make_tenant_and_user
from tests.test_clients_api import VALID_CLIENT

pytestmark = pytest.mark.db

PDF_BYTES = b"%PDF-1.4\ncontenido de prueba\n%%EOF"


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cada prueba usa su propio directorio de almacenamiento."""
    reset_storage()
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    # La configuracion esta cacheada: se limpia para que tome el nuevo valor.
    from app.core.config import get_settings

    get_settings.cache_clear()
    reset_storage()

    yield tmp_path

    reset_storage()
    get_settings.cache_clear()


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _client_id(client: AsyncClient, headers: dict[str, str]) -> str:
    """Crea un cliente y devuelve su id."""
    response = await client.post("/api/v1/clients", json=VALID_CLIENT, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestUploadDocument:
    """POST /api/v1/clients/{id}/documents."""

    async def test_uploads_pdf(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        response = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["doc_type"] == "ine"
        assert body["mime_type"] == "application/pdf"
        assert body["size_bytes"] == len(PDF_BYTES)

    async def test_stores_file_on_disk(
        self, api_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        files = list(tmp_path.rglob("*.pdf"))
        assert len(files) == 1
        assert files[0].read_bytes() == PDF_BYTES

    async def test_uses_random_filename(
        self, api_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        """RN-60: el nombre original no se conserva."""
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("mi-ine-original.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        files = list(tmp_path.rglob("*.pdf"))
        assert "mi-ine-original" not in files[0].name

    async def test_does_not_expose_file_key(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        response = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        assert "file_key" not in response.json()

    async def test_rejects_non_allowed_type(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        response = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("virus.exe", b"MZ", "application/x-msdownload")},
            data={"doc_type": "otro"},
            headers=headers,
        )

        assert response.status_code == 422
        assert "no permitido" in response.json()["detail"]

    async def test_rejects_invalid_doc_type(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        response = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "inventado"},
            headers=headers,
        )

        assert response.status_code == 422
        assert "Tipo de documento" in response.json()["detail"]

    async def test_rejects_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")

        response = await api_client.post(
            f"/api/v1/clients/{uuid4()}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        assert response.status_code == 404
        # No debe haber escrito nada en disco.
        assert list(tmp_path.rglob("*.pdf")) == []

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            f"/api/v1/clients/{uuid4()}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
        )
        assert response.status_code == 401

    async def test_upload_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        entry = await db_session.scalar(
            select(AuditLog).where(AuditLog.action == "client.document_upload")
        )
        assert entry is not None
        assert entry.after is not None
        assert entry.after["doc_type"] == "ine"


class TestDownloadDocument:
    """GET /api/v1/clients/{id}/documents/{doc_id}."""

    async def test_downloads_file(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        uploaded = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )
        document_id = uploaded.json()["id"]

        response = await api_client.get(
            f"/api/v1/clients/{client_id}/documents/{document_id}", headers=headers
        )

        assert response.status_code == 200
        assert response.content == PDF_BYTES
        assert response.headers["content-type"] == "application/pdf"

    async def test_sets_no_store_cache(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Los documentos son datos personales: no se cachean."""
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        uploaded = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        response = await api_client.get(
            f"/api/v1/clients/{client_id}/documents/{uploaded.json()['id']}",
            headers=headers,
        )

        assert "no-store" in response.headers["cache-control"]

    async def test_unknown_document_returns_404(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        response = await api_client.get(
            f"/api/v1/clients/{client_id}/documents/{uuid4()}", headers=headers
        )
        assert response.status_code == 404


class TestDeleteDocument:
    """DELETE /api/v1/clients/{id}/documents/{doc_id}."""

    async def test_deletes_file_and_record(
        self, api_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        uploaded = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )
        document_id = uploaded.json()["id"]

        assert len(list(tmp_path.rglob("*.pdf"))) == 1

        response = await api_client.delete(
            f"/api/v1/clients/{client_id}/documents/{document_id}", headers=headers
        )

        assert response.status_code == 204
        assert list(tmp_path.rglob("*.pdf")) == []

        document = await db_session.scalar(
            select(ClientDocument).where(ClientDocument.id == uuid4())
        )
        assert document is None

    async def test_unknown_document_returns_404(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        response = await api_client.delete(
            f"/api/v1/clients/{client_id}/documents/{uuid4()}", headers=headers
        )
        assert response.status_code == 404

    async def test_delete_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        uploaded = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        await api_client.delete(
            f"/api/v1/clients/{client_id}/documents/{uploaded.json()['id']}",
            headers=headers,
        )

        entry = await db_session.scalar(
            select(AuditLog).where(AuditLog.action == "client.document_delete")
        )
        assert entry is not None


class TestStorageFailures:
    """Fallos del almacenamiento y archivos que ya no existen."""

    async def test_download_when_file_missing_returns_404(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        """Si el archivo desaparecio del disco, se responde 404."""
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        uploaded = await api_client.post(
            f"/api/v1/clients/{client_id}/documents",
            files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
            data={"doc_type": "ine"},
            headers=headers,
        )

        # Se borra el archivo fisico simulando perdida de datos.
        for path in tmp_path.rglob("*.pdf"):
            path.unlink()

        response = await api_client.get(
            f"/api/v1/clients/{client_id}/documents/{uploaded.json()['id']}",
            headers=headers,
        )

        assert response.status_code == 404

    async def test_upload_rolls_back_file_when_record_fails(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Si falla el registro en base, el archivo no queda huerfano."""
        from app.services import client_service

        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")
        client_id = await _client_id(api_client, headers)

        async def _boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("fallo simulado")

        monkeypatch.setattr(client_service, "add_document", _boom)

        with pytest.raises(RuntimeError):
            await api_client.post(
                f"/api/v1/clients/{client_id}/documents",
                files={"file": ("ine.pdf", PDF_BYTES, "application/pdf")},
                data={"doc_type": "ine"},
                headers=headers,
            )

        assert list(tmp_path.rglob("*.pdf")) == []

    async def test_delete_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")

        response = await api_client.delete(
            f"/api/v1/clients/{uuid4()}/documents/{uuid4()}", headers=headers
        )
        assert response.status_code == 404

    async def test_download_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _login(api_client, "audit@test.mx")

        response = await api_client.get(
            f"/api/v1/clients/{uuid4()}/documents/{uuid4()}", headers=headers
        )
        assert response.status_code == 404
