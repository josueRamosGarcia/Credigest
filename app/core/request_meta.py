"""Utilidades para obtener datos de la peticion que se auditan.

Se centraliza aqui para que todos los endpoints pasen la IP y el cliente HTTP a
la bitacora de la misma forma.
"""

import ipaddress
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class RequestMeta:
    """Datos de la peticion que se guardan en la auditoria."""

    ip_address: str | None
    user_agent: str | None


def parse_ip(raw: str | None) -> str | None:
    """Normaliza una IP valida (IPv4 o IPv6) o devuelve `None`.

    PostgreSQL almacena `audit_log.ip_address` en una columna `INET`: un valor
    malformado (como texto arbitrario en `X-Forwarded-For` o `"testclient"`)
    provocaria `DataError` al insertar.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def request_meta(request: Request) -> RequestMeta:
    """Extrae la IP y el user-agent de una peticion.

    Detras de un proxy, la IP real llega en `X-Forwarded-For`. Se toma la
    primera de la lista si es una IP valida; de lo contrario se usa
    `request.client.host` (tambien validada).

    Args:
        request: Peticion de FastAPI.

    Returns:
        La IP valida y el user-agent, con `None` si no estan disponibles.
    """
    forwarded = request.headers.get("x-forwarded-for")
    ip_address = parse_ip(forwarded.split(",")[0]) if forwarded else None

    if ip_address is None and request.client:
        ip_address = parse_ip(request.client.host)

    return RequestMeta(
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
    )
