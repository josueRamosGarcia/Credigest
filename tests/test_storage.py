"""Pruebas de la capa de almacenamiento."""

from pathlib import Path
from uuid import uuid4

import pytest

from app.core.storage import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_BYTES,
    FileNotFoundInStorageError,
    InvalidFileError,
    LocalStorage,
    StorageError,
    validate_upload,
)

TENANT = uuid4()
CLIENT = uuid4()


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """Almacen temporal aislado por prueba."""
    return LocalStorage(tmp_path)


class TestValidateUpload:
    """Validaciones previas a escribir (RNF-09)."""

    @pytest.mark.parametrize("mime", sorted(ALLOWED_MIME_TYPES))
    def test_accepts_allowed_types(self, mime: str) -> None:
        validate_upload(b"contenido", mime)

    def test_rejects_empty_file(self) -> None:
        with pytest.raises(InvalidFileError, match="vacio"):
            validate_upload(b"", "application/pdf")

    def test_rejects_oversized_file(self) -> None:
        big = b"x" * (MAX_FILE_BYTES + 1)
        with pytest.raises(InvalidFileError, match="10 MB"):
            validate_upload(big, "application/pdf")

    def test_accepts_exactly_max_size(self) -> None:
        exact = b"x" * MAX_FILE_BYTES
        validate_upload(exact, "application/pdf")

    def test_rejects_disallowed_type(self) -> None:
        with pytest.raises(InvalidFileError, match="no permitido"):
            validate_upload(b"contenido", "application/x-msdownload")

    def test_rejects_executable(self) -> None:
        with pytest.raises(InvalidFileError):
            validate_upload(b"MZ", "application/x-dosexec")


class TestLocalStorage:
    """Guardado, lectura y borrado."""

    def test_saves_file(self, storage: LocalStorage, tmp_path: Path) -> None:
        key = storage.save(TENANT, CLIENT, "ine", b"contenido", "application/pdf")

        assert (tmp_path / key).exists()
        assert key.startswith(f"{TENANT}/{CLIENT}/ine-")
        assert key.endswith(".pdf")

    def test_reads_saved_file(self, storage: LocalStorage) -> None:
        key = storage.save(TENANT, CLIENT, "ine", b"contenido", "application/pdf")

        assert storage.read(key) == b"contenido"

    def test_generates_unique_names(self, storage: LocalStorage) -> None:
        first = storage.save(TENANT, CLIENT, "ine", b"a", "application/pdf")
        second = storage.save(TENANT, CLIENT, "ine", b"b", "application/pdf")

        assert first != second

    def test_uses_extension_from_mime(self, storage: LocalStorage) -> None:
        assert storage.save(TENANT, CLIENT, "ine", b"a", "image/jpeg").endswith(".jpg")
        assert storage.save(TENANT, CLIENT, "ine", b"a", "image/png").endswith(".png")

    def test_exists(self, storage: LocalStorage) -> None:
        key = storage.save(TENANT, CLIENT, "ine", b"a", "application/pdf")

        assert storage.exists(key) is True
        assert storage.exists("no/existe.pdf") is False

    def test_deletes_file(self, storage: LocalStorage, tmp_path: Path) -> None:
        key = storage.save(TENANT, CLIENT, "ine", b"a", "application/pdf")

        storage.delete(key)

        assert not (tmp_path / key).exists()

    def test_delete_is_idempotent(self, storage: LocalStorage) -> None:
        storage.delete("no/existe.pdf")

    def test_read_missing_file(self, storage: LocalStorage) -> None:
        with pytest.raises(FileNotFoundInStorageError):
            storage.read("no/existe.pdf")

    def test_rejects_traversal_in_key(self, storage: LocalStorage) -> None:
        """Una clave manipulada no debe salir del directorio raiz."""
        with pytest.raises(StorageError, match="no valida"):
            storage.read("../../etc/passwd")

    def test_rejects_absolute_path(self, storage: LocalStorage) -> None:
        with pytest.raises(StorageError):
            storage.read("/etc/passwd")

    def test_separates_tenants(self, storage: LocalStorage) -> None:
        other_tenant = uuid4()
        key = storage.save(other_tenant, CLIENT, "ine", b"a", "application/pdf")

        assert key.startswith(str(other_tenant))

    def test_validates_before_writing(self, storage: LocalStorage, tmp_path: Path) -> None:
        with pytest.raises(InvalidFileError):
            storage.save(TENANT, CLIENT, "ine", b"", "application/pdf")

        # No debe haber creado el directorio del cliente.
        assert not (tmp_path / str(TENANT) / str(CLIENT)).exists()
