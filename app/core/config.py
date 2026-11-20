"""Configuracion de la aplicacion leida desde variables de entorno."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "credigest-desarrollo-cambiar-en-produccion-32b"
_LOCAL_ENVIRONMENTS = frozenset({"local", "development", "dev", "test"})


class Settings(BaseSettings):
    """Valores de configuracion del backend.

    Todos se pueden sobrescribir con variables de entorno o un archivo .env.
    No se incluyen valores secretos por defecto en produccion.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Credigest API"
    environment: str = "local"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/credigest"
    timezone: str = "America/Mexico_City"

    #: Secreto para firmar los JWT. En produccion es obligatorio definirlo por
    #: variable de entorno. Debe tener al menos 32 bytes (RFC 7518 §3.2).
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"

    #: Origenes permitidos para CORS, separados por coma (ej. "https://app.credigest.mx").
    cors_origins: str = ""

    #: Duracion del token de acceso y del de refresco (RNF-07).
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    #: Limite de intentos de login por IP y su ventana en segundos (RNF-10).
    login_rate_limit: int = 5
    login_rate_window: int = 60

    #: Directorio donde se guardan los documentos de los clientes (RN-60).
    storage_dir: str = "storage"

    @property
    def cors_origins_list(self) -> list[str]:
        """Lista limpia de origenes CORS configurados."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_production_secret(self) -> "Settings":
        """Impide arrancar fuera de entornos locales con el secreto por defecto."""
        if (
            self.environment.lower() not in _LOCAL_ENVIRONMENTS
            and (self.jwt_secret == _DEV_JWT_SECRET or len(self.jwt_secret.encode("utf-8")) < 32)
        ):
            raise ValueError(
                "En produccion es obligatorio definir JWT_SECRET con al menos 32 bytes."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia unica de configuracion (cacheada)."""
    return Settings()
