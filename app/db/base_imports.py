"""Importa los modelos para que Alembic los registre en Base.metadata.

Cuando se agregue un modelo nuevo en app/models/, debe importarse aqui.
Sin este import, `alembic revision --autogenerate` genera migraciones vacias.
"""

from app.models.system_setting import SystemSetting  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = ["SystemSetting", "Tenant", "User"]
