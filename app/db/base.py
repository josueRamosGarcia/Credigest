"""Base declarativa de SQLAlchemy.

Los modelos deben importarse en app/db/base_imports.py para que Alembic
los detecte al generar migraciones.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Clase base de todos los modelos."""
