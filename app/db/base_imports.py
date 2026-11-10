"""Importa los modelos para que Alembic los registre en Base.metadata.

Cuando se agregue un modelo nuevo en app/models/, debe importarse aqui.
Sin este import, `alembic revision --autogenerate` genera migraciones vacias.
"""

from app.models.audit_log import AuditLog  # noqa: F401
from app.models.client import Client, ClientDocument, ClientReference  # noqa: F401
from app.models.collection_route import CollectionRoute, CollectionRouteItem  # noqa: F401
from app.models.loan import Installment, Loan  # noqa: F401
from app.models.payment import Payment, PaymentApplication  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.system_setting import SystemSetting  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = [
    "AuditLog",
    "Client",
    "ClientDocument",
    "ClientReference",
    "CollectionRoute",
    "CollectionRouteItem",
    "Installment",
    "Loan",
    "Payment",
    "PaymentApplication",
    "RefreshToken",
    "SystemSetting",
    "Tenant",
    "User",
]
