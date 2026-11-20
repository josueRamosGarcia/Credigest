"""Esquemas de usuarios y parametros globales del sistema."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH

UserRole = Literal["admin", "prestamista", "cobrador"]
LoanSchemeLiteral = Literal["simple", "saldo_insoluto", "cuota_fija"]

#: Permisos granulares soportados en el MVP (RN-61, RF-05).
ALLOWED_PERMISSIONS = frozenset(
    {
        "create_user",
        "edit_settings",
        "view_dashboard",
        "view_audit",
        "create_client",
        "edit_client",
        "create_loan",
        "edit_rate",
        "cancel_payment",
        "register_payment",
        "view_assigned_routes",
    }
)


def _validate_password_value(value: str) -> str:
    """Valida longitud y tamano en bytes de una contrasena."""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"La contrasena debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"La contrasena no puede superar {MAX_PASSWORD_BYTES} bytes."
        )
    return value


def _validate_permissions_map(value: dict[str, bool]) -> dict[str, bool]:
    """Verifica que solo se envien claves de permisos conocidas."""
    unknown = set(value) - ALLOWED_PERMISSIONS
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"Permisos no reconocidos: {joined}.")
    return {key: bool(flag) for key, flag in value.items()}


class UserCreate(BaseModel):
    """Datos para dar de alta un usuario dentro de la financiera."""

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: Annotated[str, Field(min_length=2, max_length=150)]
    email: EmailStr
    phone: Annotated[str | None, Field(default=None, max_length=20)] = None
    role: UserRole
    permissions: dict[str, bool] = Field(default_factory=dict)
    password: str | None = Field(
        default=None,
        description=(
            "Contrasena inicial opcional. Si se omite, el sistema genera una "
            "contrasena temporal (RF-06)."
        ),
    )

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_password_value(value)

    @field_validator("permissions")
    @classmethod
    def _check_permissions(cls, value: dict[str, bool]) -> dict[str, bool]:
        return _validate_permissions_map(value)


class UserUpdate(BaseModel):
    """Campos editables de un usuario."""

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: Annotated[str | None, Field(default=None, min_length=2, max_length=150)] = (
        None
    )
    phone: Annotated[str | None, Field(default=None, max_length=20)] = None
    role: UserRole | None = None
    permissions: dict[str, bool] | None = None

    @field_validator("permissions")
    @classmethod
    def _check_permissions(
        cls, value: dict[str, bool] | None
    ) -> dict[str, bool] | None:
        if value is None:
            return None
        return _validate_permissions_map(value)


class UserStatusChange(BaseModel):
    """Cambio de estado activo/inactivo de un usuario."""

    is_active: bool


class UserPasswordResetRequest(BaseModel):
    """Solicitud de restablecimiento de contrasena por el Administrador (RF-06)."""

    password: str | None = Field(
        default=None,
        description=(
            "Contrasena temporal opcional. Si no se indica, se genera una aleatoria."
        ),
    )

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_password_value(value)


class UserRead(BaseModel):
    """Representacion publica de un usuario."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    full_name: str
    email: EmailStr
    phone: str | None
    role: str
    permissions: dict[str, bool]
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreatedResponse(UserRead):
    """Respuesta al crear un usuario; incluye la contrasena temporal si aplica."""

    temporary_password: str | None = None


class UserPasswordResetResponse(BaseModel):
    """Respuesta al restablecer la contrasena de un usuario."""

    user_id: UUID
    temporary_password: str


class UserListResponse(BaseModel):
    """Lista paginada de usuarios."""

    items: list[UserRead]
    total: int
    page: int
    page_size: int


class SystemSettingRead(BaseModel):
    """Configuracion global vigente de la financiera."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    default_late_fee_rate: Decimal
    default_scheme: str
    grace_days: int
    timezone: str
    updated_at: datetime


class SystemSettingUpdate(BaseModel):
    """Actualizacion de parametros globales (RF-09 a RF-11)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    default_late_fee_rate: Annotated[
        Decimal, Field(ge=Decimal("0"), le=Decimal("1"))
    ]
    default_scheme: LoanSchemeLiteral
    grace_days: Annotated[int, Field(ge=0, le=90)]
    timezone: Annotated[str, Field(min_length=3, max_length=50)] = (
        "America/Mexico_City"
    )

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Zona horaria no valida: {value!r}.") from exc
        return value

