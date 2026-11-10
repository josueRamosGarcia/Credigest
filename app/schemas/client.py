"""Esquemas de clientes."""

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.validation import CurpError, parse_curp


class ClientReferenceCreate(BaseModel):
    """Referencia personal del cliente."""

    name: Annotated[str, Field(min_length=1, max_length=150)]
    relationship: Annotated[str, Field(min_length=1, max_length=80)]
    phone: Annotated[str, Field(min_length=7, max_length=20)]
    address: Annotated[str, Field(min_length=1, max_length=500)]


class ClientReferenceRead(BaseModel):
    """Referencia personal tal como se devuelve."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    name: str
    #: La API expone `relationship`; el atributo de Python se llama `relation`
    #: para no tapar la funcion homonima de SQLAlchemy.
    relationship: str = Field(validation_alias="relation")
    phone: str
    address: str


class ClientCreate(BaseModel):
    """Datos para registrar un cliente.

    La CURP se valida aqui para responder 422 con un mensaje claro antes de
    llegar al servicio.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Maria Lopez Perez",
                "curp": "LOPJ850312MDFZRN07",
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
        }
    )

    full_name: Annotated[str, Field(min_length=3, max_length=200)]
    #: La longitud no se valida aqui: se deja al validador de CURP para que el
    #: mensaje de error sea el mismo en todos los casos y en espanol.
    curp: Annotated[str, Field(max_length=30)]
    phone: Annotated[str, Field(min_length=7, max_length=20)]
    address: Annotated[str, Field(min_length=5, max_length=500)]
    zone: Annotated[str | None, Field(max_length=80)] = None
    notes: Annotated[str | None, Field(max_length=1000)] = None
    references: Annotated[list[ClientReferenceCreate], Field(max_length=10)] = Field(
        default_factory=list
    )

    @field_validator("curp")
    @classmethod
    def _validate_curp(cls, value: str) -> str:
        """Normaliza y valida la CURP (RN-55)."""
        try:
            return parse_curp(value).curp
        except CurpError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("full_name", "phone", "address")
    @classmethod
    def _strip(cls, value: str) -> str:
        """Quita espacios sobrantes."""
        return value.strip()


class ClientUpdate(BaseModel):
    """Campos editables de un cliente.

    La CURP no se puede cambiar: identifica a la persona y esta ligada a sus
    documentos. Si se capturo mal, se corrige con un proceso administrativo.
    """

    full_name: Annotated[str | None, Field(min_length=3, max_length=200)] = None
    phone: Annotated[str | None, Field(min_length=7, max_length=20)] = None
    address: Annotated[str | None, Field(min_length=5, max_length=500)] = None
    zone: Annotated[str | None, Field(max_length=80)] = None
    notes: Annotated[str | None, Field(max_length=1000)] = None


class ClientRead(BaseModel):
    """Cliente tal como se devuelve a la API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    curp: str
    phone: str
    address: str
    zone: str | None
    birth_date: date | None
    status: str
    notes: str | None


class ClientDetail(ClientRead):
    """Cliente con sus referencias.

    Los documentos no se incluyen: se consultan por separado porque requieren
    URLs firmadas con expiracion (RN-60).
    """

    references: list[ClientReferenceRead] = Field(default_factory=list)


class ClientListResponse(BaseModel):
    """Pagina de clientes."""

    items: list[ClientRead]
    total: int
    page: int
    page_size: int


class ClientStatusChange(BaseModel):
    """Cambio de estado de un cliente."""

    status: str = Field(pattern="^(activo|inactivo)$")


class DocumentRead(BaseModel):
    """Metadatos de un documento, sin la URL de descarga."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doc_type: str
    mime_type: str
    size_bytes: int
