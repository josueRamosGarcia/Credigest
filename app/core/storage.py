"""Almacenamiento de archivos.

Se usa una interfaz simple (`Storage`) con una implementacion en disco local. El
dia que se necesite S3 o MinIO, se agrega otra implementacion y se cambia la
fabrica: los endpoints no se tocan.

Reglas que aplican:
- RNF-09: se valida el tipo MIME y el tamano maximo antes de guardar.
- RN-60: el nombre del archivo es aleatorio y la ruta interna nunca se expone.
"""

import shutil
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import get_settings

#: Tipos MIME aceptados para documentos de cliente.
ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

#: Extension sugerida por tipo MIME.
MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

#: Tamano maximo por archivo: 10 MB, segun RNF-09.
MAX_FILE_BYTES = 10 * 1024 * 1024


class StorageError(Exception):
    """Error al guardar o leer un archivo."""


class InvalidFileError(StorageError):
    """El archivo no cumple las validaciones de tipo o tamano."""


class FileNotFoundInStorageError(StorageError):
    """El archivo solicitado no existe en el almacenamiento."""


class Storage(Protocol):
    """Contrato de un almacen de archivos."""

    def save(
        self,
        tenant_id: UUID,
        client_id: UUID,
        doc_type: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        """Guarda un archivo y devuelve su clave interna."""
        ...

    def read(self, key: str) -> bytes:
        """Devuelve el contenido de un archivo."""
        ...

    def delete(self, key: str) -> None:
        """Elimina un archivo si existe."""
        ...

    def exists(self, key: str) -> bool:
        """Indica si la clave existe."""
        ...


def validate_upload(content: bytes, mime_type: str) -> None:
    """Valida el tipo y el tamano antes de escribir nada.

    Raises:
        InvalidFileError: Si el tipo no esta permitido o el archivo esta vacio
            o excede el limite.
    """
    if not content:
        raise InvalidFileError("El archivo esta vacio.")

    if len(content) > MAX_FILE_BYTES:
        limit_mb = MAX_FILE_BYTES // (1024 * 1024)
        raise InvalidFileError(f"El archivo supera el limite de {limit_mb} MB.")

    if mime_type not in ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_MIME_TYPES))
        raise InvalidFileError(
            f"Tipo de archivo no permitido: {mime_type}. Se aceptan: {allowed}."
        )


class LocalStorage:
    """Guarda los archivos en disco, bajo el directorio configurado.

    La clave tiene la forma ``{tenant_id}/{client_id}/{doc_type}-{aleatorio}{ext}``
    y se usa como ruta relativa dentro de la raiz.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        tenant_id: UUID,
        client_id: UUID,
        doc_type: str,
        content: bytes,
        mime_type: str,
    ) -> str:
        """Escribe el archivo y devuelve la clave relativa."""
        validate_upload(content, mime_type)

        extension = MIME_EXTENSIONS.get(mime_type, "")
        filename = f"{doc_type}-{uuid4().hex}{extension}"
        key = f"{tenant_id}/{client_id}/{filename}"

        target = self._root / key
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        except OSError as exc:
            raise StorageError(f"No se pudo guardar el archivo: {exc}") from exc

        return key

    def read(self, key: str) -> bytes:
        """Lee un archivo por su clave."""
        target = self._safe_path(key)
        if not target.exists():
            raise FileNotFoundInStorageError("El archivo ya no esta disponible.")
        return target.read_bytes()

    def delete(self, key: str) -> None:
        """Elimina un archivo. No falla si ya no existe."""
        target = self._safe_path(key)
        target.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        """Indica si la clave existe."""
        return self._safe_path(key).exists()

    def _safe_path(self, key: str) -> Path:
        """Resuelve la ruta y evita salir del directorio raiz.

        Sin esta comprobacion, una clave manipulada como ``../../etc/passwd``
        permitiria leer archivos del sistema.
        """
        candidate = (self._root / key).resolve()
        root = self._root.resolve()

        if not candidate.is_relative_to(root):
            raise StorageError("Ruta de archivo no valida.")

        return candidate


_local_storage: LocalStorage | None = None


def get_storage() -> Storage:
    """Devuelve la implementacion configurada (una sola instancia)."""
    global _local_storage

    if _local_storage is None:
        settings = get_settings()
        _local_storage = LocalStorage(Path(settings.storage_dir))

    return _local_storage


def reset_storage() -> None:
    """Reinicia la instancia cacheada. Se usa en pruebas."""
    global _local_storage
    _local_storage = None


def clear_directory(path: Path) -> None:
    """Borra el contenido de un directorio. Util en pruebas."""
    if path.exists():
        shutil.rmtree(path)
