"""Esquemas de autenticacion."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Credenciales del usuario."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "admin@demo.mx", "password": "clave-segura-123"}
        }
    )

    email: EmailStr = Field(description="Correo del usuario. Es unico global.")
    password: Annotated[str, Field(min_length=1, description="Contrasena en claro.")]


class RefreshRequest(BaseModel):
    """Token de refresco que se quiere canjear."""

    refresh_token: Annotated[str, Field(min_length=1)]


class TokenPair(BaseModel):
    """Par de tokens devuelto al iniciar sesion o al refrescar."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos de vida del access token.")


class CurrentUser(BaseModel):
    """Datos del usuario autenticado."""

    id: UUID
    tenant_id: UUID
    full_name: str
    email: EmailStr
    role: str
    permissions: dict[str, bool]
    tenant_name: str
    tenant_slug: str | None
    tenant_plan: str
