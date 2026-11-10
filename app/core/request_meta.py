"""Utilidades para obtener datos de la peticion que se auditan.

Se centraliza aqui para que todos los endpoints pasen la IP y el cliente HTTP a
la bitacora de la misma forma.
"""

from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class RequestMeta:
    """Datos de la peticion que se guardan en la auditoria."""

    ip_address: str | None
    user_agent: str | None


def request_meta(request: Request) -> RequestMeta:
    """Extrae la IP y el user-agent de una peticion.

    Detras de un proxy, la IP real llega en `X-Forwarded-For`. Se toma la
    primera de la lista, que es la del cliente original.

    Args:
        request: Peticion de FastAPI.

    Returns:
        La IP y el user-agent, con `None` si no estan disponibles.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip_address = forwarded.split(",")[0].strip() or None
    else:
        ip_address = request.client.host if request.client else None

    return RequestMeta(
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
    )
