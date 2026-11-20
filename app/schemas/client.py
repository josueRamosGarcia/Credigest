"""Esquemas de clientes."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.validation import CurpError, parse_curp

Latitude = Annotated[
    Decimal,
    Field(ge=Decimal("-90"), le=Decimal("90"), max_digits=9, decimal_places=6),
]
Longitude = Annotated[
    Decimal,
    Field(ge=Decimal("-180"), le=Decimal("180"), max_digits=9, decimal_places=6),
]


def compose_address(
    *,
    street: str | None = None,
    exterior_number: str | None = None,
    neighborhood: str | None = None,
    postal_code: str | None = None,
    city: str | None = None,
    state: str | None = None,
) -> str:
    """Arma una direccion legible a partir de sus componentes separados."""
    parts: list[str] = []
    street_line = " ".join(p for p in [street, exterior_number] if p)
    if street_line:
        parts.append(street_line)
    if neighborhood:
        parts.append(f"Col. {neighborhood}")
    if postal_code:
        parts.append(f"C.P. {postal_code}")
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    return ", ".join(parts)


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
                "curp": "LOPJ850312MDFZRN00",
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
    address: Annotated[str | None, Field(max_length=500)] = None
    street: Annotated[str | None, Field(max_length=200)] = None
    exterior_number: Annotated[str | None, Field(max_length=30)] = None
    neighborhood: Annotated[str | None, Field(max_length=150)] = None
    postal_code: Annotated[str | None, Field(max_length=10)] = None
    city: Annotated[str | None, Field(max_length=100)] = None
    state: Annotated[str | None, Field(max_length=100)] = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
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

    @field_validator("full_name", "phone")
    @classmethod
    def _strip(cls, value: str) -> str:
        """Quita espacios sobrantes."""
        return value.strip()

    @field_validator(
        "address",
        "street",
        "exterior_number",
        "neighborhood",
        "postal_code",
        "city",
        "state",
        "zone",
        "notes",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        """Normaliza textos opcionales convirtiendo vacios en None."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def _ensure_address_and_coords(self) -> "ClientCreate":
        """Arma `address` desde los campos separados si no se envio directamente."""
        if not self.address:
            composed = compose_address(
                street=self.street,
                exterior_number=self.exterior_number,
                neighborhood=self.neighborhood,
                postal_code=self.postal_code,
                city=self.city,
                state=self.state,
            )
            self.address = composed or None

        if not self.address or len(self.address) < 5:
            raise ValueError("La direccion debe tener al menos 5 caracteres.")

        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Debes indicar tanto la latitud como la longitud.")

        return self


class ClientUpdate(BaseModel):
    """Campos editables de un cliente.

    La CURP no se puede cambiar: identifica a la persona y esta ligada a sus
    documentos. Si se capturo mal, se corrige con un proceso administrativo.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: Annotated[str | None, Field(min_length=3, max_length=200)] = None
    phone: Annotated[str | None, Field(min_length=7, max_length=20)] = None
    address: Annotated[str | None, Field(min_length=5, max_length=500)] = None
    street: Annotated[str | None, Field(max_length=200)] = None
    exterior_number: Annotated[str | None, Field(max_length=30)] = None
    neighborhood: Annotated[str | None, Field(max_length=150)] = None
    postal_code: Annotated[str | None, Field(max_length=10)] = None
    city: Annotated[str | None, Field(max_length=100)] = None
    state: Annotated[str | None, Field(max_length=100)] = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    zone: Annotated[str | None, Field(max_length=80)] = None
    notes: Annotated[str | None, Field(max_length=1000)] = None

    @field_validator("full_name", "phone", "address")
    @classmethod
    def _reject_explicit_null(cls, value: str | None) -> str:
        """Impide enviar `null` explicito en columnas NOT NULL."""
        if value is None:
            raise ValueError("Este campo no puede ser nulo.")
        return value

    @model_validator(mode="after")
    def _validate_coords_pair(self) -> "ClientUpdate":
        """Si se envia latitud o longitud, ambas deben venir juntas (o ambas nulas)."""
        sent = self.model_fields_set
        if ("latitude" in sent or "longitude" in sent) and (
            (self.latitude is None) != (self.longitude is None)
        ):
            raise ValueError("Debes indicar tanto la latitud como la longitud.")
        return self


class ClientRead(BaseModel):
    """Cliente tal como se devuelve a la API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    curp: str
    phone: str
    address: str
    street: str | None = None
    exterior_number: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    zone: str | None
    birth_date: date | None
    status: str
    notes: str | None
    has_portal_pin: bool = False


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


class PortalPinSetRequest(BaseModel):
    """Solicitud para asignar o generar un PIN de 6 digitos al cliente."""

    pin: Annotated[
        str | None,
        Field(default=None, pattern=r"^\d{6}$", description="PIN opcional de 6 digitos."),
    ] = None


class PortalPinResponse(BaseModel):
    """Respuesta con el PIN en claro (solo al momento de generarlo) y enlace de WhatsApp."""

    client_id: UUID
    pin: str
    whatsapp_url: str

