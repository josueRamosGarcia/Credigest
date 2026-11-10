"""Configuracion de la aplicacion leida desde variables de entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de configuracion del backend.

    Todos se pueden sobrescribir con variables de entorno o un archivo .env.
    No se incluyen valores secretos por defecto.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Credigest API"
    environment: str = "local"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/credigest"
    timezone: str = "America/Mexico_City"

    #: Secreto para firmar los JWT. En produccion es obligatorio definirlo por
    #: variable de entorno. Debe tener al menos 32 bytes (RFC 7518 §3.2).
    jwt_secret: str = "credigest-desarrollo-cambiar-en-produccion-32b"
    jwt_algorithm: str = "HS256"

    #: Duracion del token de acceso y del de refresco (RNF-07).
    access_token_minutes: int = 15
    refresh_token_days: int = 7


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia unica de configuracion (cacheada)."""
    return Settings()
