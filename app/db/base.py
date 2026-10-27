"""Base declarativa de SQLAlchemy y utilidades compartidas por los modelos.

Los modelos deben importarse en app/db/base_imports.py para que Alembic
los detecte al generar migraciones.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Convencion de nombres para restricciones e indices.
#: Sin esto, PostgreSQL genera nombres aleatorios y las migraciones se vuelven
#: dificiles de revertir.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Clase base de todos los modelos."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Agrega una llave primaria UUID generada en la aplicacion.

    Se genera en Python y no en la base porque asi el objeto tiene su id antes
    del `commit`, lo que simplifica la respuesta de la API.
    """

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    """Agrega fechas de creacion y ultima actualizacion en UTC.

    `timestamptz` guarda la zona horaria. La aplicacion muestra las fechas en
    `America/Mexico_City`, pero la base siempre almacena en UTC.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
