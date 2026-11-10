"""Limite de intentos por IP.

Protege el login de ataques de fuerza bruta (RNF-10). El contador vive en memoria
del proceso, lo que es suficiente para un despliegue de un solo worker.

Si mas adelante se corre con varios workers o varias instancias, este modulo debe
sustituirse por un contador compartido en Redis. La interfaz esta pensada para que
ese cambio no afecte a los endpoints.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

from app.core.config import get_settings

#: Intentos permitidos dentro de la ventana.
DEFAULT_LIMIT = 5

#: Duracion de la ventana en segundos.
DEFAULT_WINDOW_SECONDS = 60


@dataclass
class _Bucket:
    """Intentos registrados para una clave."""

    timestamps: deque[float] = field(default_factory=deque)


class RateLimiter:
    """Limitador de ventana deslizante por clave.

    Guarda solo los intentos dentro de la ventana vigente, asi que la memoria
    usada es proporcional al numero de IPs activas y no al trafico historico.
    """

    def __init__(
        self,
        limit: int = DEFAULT_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        if limit < 1:
            raise ValueError("El limite debe ser al menos 1.")
        if window_seconds < 1:
            raise ValueError("La ventana debe ser de al menos 1 segundo.")

        self._limit = limit
        self._window = window_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    @property
    def limit(self) -> int:
        """Intentos permitidos por ventana."""
        return self._limit

    @property
    def window_seconds(self) -> int:
        """Duracion de la ventana."""
        return self._window

    def _prune(self, bucket: _Bucket, now: float) -> None:
        """Descarta los intentos fuera de la ventana."""
        cutoff = now - self._window
        while bucket.timestamps and bucket.timestamps[0] <= cutoff:
            bucket.timestamps.popleft()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        """Consulta si una clave puede intentar de nuevo.

        No registra el intento: eso lo hace `hit` cuando el login falla.

        Args:
            key: Identificador del cliente, normalmente la IP.
            now: Marca de tiempo; se inyecta en pruebas.

        Returns:
            Una tupla (permitido, segundos_para_reintentar). El segundo valor es
            cero cuando esta permitido.
        """
        current = time.monotonic() if now is None else now

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return (True, 0)

            self._prune(bucket, current)
            if len(bucket.timestamps) < self._limit:
                return (True, 0)

            oldest = bucket.timestamps[0]
            retry_after = max(1, int(self._window - (current - oldest)) + 1)
            return (False, retry_after)

    def hit(self, key: str, *, now: float | None = None) -> None:
        """Registra un intento fallido para la clave."""
        current = time.monotonic() if now is None else now

        with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket())
            self._prune(bucket, current)
            bucket.timestamps.append(current)

    def reset(self, key: str) -> None:
        """Borra el historial de una clave.

        Se llama al iniciar sesion correctamente: un usuario legitimo no debe
        quedar penalizado por haberse equivocado antes.
        """
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        """Borra todos los contadores. Util en pruebas."""
        with self._lock:
            self._buckets.clear()


def _build_login_limiter() -> RateLimiter:
    """Crea el limitador con la configuracion del entorno."""
    settings = get_settings()
    return RateLimiter(limit=settings.login_rate_limit, window_seconds=settings.login_rate_window)


#: Instancia usada por los endpoints de autenticacion.
login_limiter = _build_login_limiter()
