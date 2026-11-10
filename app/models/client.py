"""Modelos de clientes.

Un cliente pertenece a una financiera (tenant) y concentra sus datos
personales, documentos y referencias.

Reglas que aplican:
- RN-55: la CURP se valida y se guarda normalizada.
- RN-56: la CURP es unica por tenant, no global.
- RN-57: no se elimina un cliente con historial; solo se desactiva.
- RN-60: los documentos se guardan con nombre aleatorio fuera de la base; aqui
  solo vive la referencia.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Client(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una persona que recibe prestamos de la financiera."""

    __tablename__ = "client"
    __table_args__ = (
        # RN-56: la misma CURP puede existir en dos financieras distintas.
        UniqueConstraint("tenant_id", "curp", name="uq_client_tenant_id_curp"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    #: CURP normalizada en mayusculas (RN-55).
    curp: Mapped[str] = mapped_column(String(18), nullable=False, index=True)

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)

    #: Zona usada para armar las rutas de cobro.
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    #: Fecha de nacimiento extraida de la CURP al registrar al cliente.
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum("activo", "inactivo", name="client_status"),
        nullable=False,
        default="activo",
        server_default="activo",
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    references: Mapped[list["ClientReference"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="ClientReference.created_at",
    )

    documents: Mapped[list["ClientDocument"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Representacion de depuracion sin datos personales (RNF-09)."""
        return f"<Client {self.id} status={self.status}>"


class ClientDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Un documento digitalizado del cliente (INE, comprobante de domicilio)."""

    __tablename__ = "client_document"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    doc_type: Mapped[str] = mapped_column(
        Enum("ine", "comprobante_domicilio", "otro", name="document_type"),
        nullable=False,
    )

    #: Ruta en el almacenamiento de objetos. Nunca es una URL publica (RN-60).
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    uploaded_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    client: Mapped[Client] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        """Representacion de depuracion sin exponer la ruta del archivo."""
        return f"<ClientDocument {self.id} type={self.doc_type}>"


class ClientReference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una referencia personal del cliente."""

    __tablename__ = "client_reference"

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("client.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    #: El atributo se llama `relation` porque `relationship` es el nombre de la
    #: funcion de SQLAlchemy que define relaciones entre modelos.
    relation: Mapped[str] = mapped_column("relationship", String(80), nullable=False)

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)

    client: Mapped[Client] = relationship(back_populates="references")

    def __repr__(self) -> str:
        """Representacion de depuracion sin datos personales."""
        return f"<ClientReference {self.id}>"
