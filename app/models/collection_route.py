"""Modelos de rutas de cobro.

Una ruta agrupa las cuotas que un cobrador debe visitar en un dia para una zona
determinada (RN-42). El orden de visita es editable por el cobrador (RN-44).

Reglas que aplican:
- RN-42: la ruta agrupa cuotas pendientes o vencidas por zona y fecha.
- RN-43: solo entran clientes con cuotas con vencimiento hasta la fecha de ruta.
- RN-44: el orden por defecto es por fecha de vencimiento y nombre.
- RN-45: un cobrador solo ve sus rutas asignadas.
- RN-46: registrar un pago marca el item como pagado.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CollectionRoute(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una ruta de cobro para un cobrador, una zona y un dia."""

    __tablename__ = "collection_route"
    __table_args__ = (
        Index("ix_collection_route_cobrador_date", "cobrador_id", "route_date"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cobrador_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    zone: Mapped[str] = mapped_column(String(80), nullable=False)

    route_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        Enum("borrador", "activa", "cerrada", name="route_status"),
        nullable=False,
        default="borrador",
        server_default="borrador",
    )

    #: Notas de la jornada, por ejemplo incidencias del dia.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["CollectionRouteItem"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="CollectionRouteItem.order_index",
    )

    def __repr__(self) -> str:
        """Representacion de depuracion."""
        return f"<CollectionRoute {self.zone} {self.route_date} status={self.status}>"


class CollectionRouteItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una parada de la ruta: un cliente con una cuota a cobrar."""

    __tablename__ = "collection_route_item"
    __table_args__ = (
        # Una misma cuota no debe aparecer dos veces en la misma ruta.
        UniqueConstraint("route_id", "installment_id", name="uq_route_item_route_installment"),
    )

    route_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("collection_route.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("client.id", ondelete="RESTRICT"),
        nullable=False,
    )

    loan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("loan.id", ondelete="RESTRICT"),
        nullable=False,
    )

    installment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("installment.id", ondelete="RESTRICT"),
        nullable=False,
    )

    #: Orden de visita dentro de la ruta (RN-44).
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    visit_status: Mapped[str] = mapped_column(
        Enum("pendiente", "pagado", "no_pagado", name="visit_status"),
        nullable=False,
        default="pendiente",
        server_default="pendiente",
    )

    #: Pago registrado durante esta visita, si lo hubo.
    payment_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("payment.id", ondelete="SET NULL"),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    route: Mapped[CollectionRoute] = relationship(back_populates="items")

    def __repr__(self) -> str:
        """Representacion de depuracion sin datos del cliente."""
        return f"<CollectionRouteItem order={self.order_index} status={self.visit_status}>"
