"""Endpoints de documentos de clientes.

La subida valida tipo y tamano antes de escribir (RNF-09). La descarga usa una
URL firmada de corta duracion, nunca una ruta directa al archivo (RN-60).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.core.request_meta import request_meta
from app.core.storage import (
    InvalidFileError,
    StorageError,
    get_storage,
)
from app.db.session import get_session
from app.schemas.client import DocumentRead
from app.services import audit_service, client_service

router = APIRouter(prefix="/clients", tags=["documentos"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _not_found(message: str) -> HTTPException:
    """Error uniforme de recurso inexistente."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


@router.post(
    "/{client_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Subir un documento",
    description=(
        "Acepta PDF, JPG, PNG o WEBP de hasta 10 MB. El nombre del archivo se "
        "reemplaza por uno aleatorio y la ruta interna nunca se expone."
    ),
)
async def upload_document(
    client_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
    request: Request,
    file: Annotated[UploadFile, File(description="Archivo del documento")],
    doc_type: Annotated[
        str,
        Form(description="Tipo: ine, comprobante_domicilio u otro"),
    ] = "otro",
) -> DocumentRead:
    """Sube un documento y lo asocia al cliente.

    Raises:
        HTTPException: 404 si el cliente no existe; 422 si el archivo no cumple
            las validaciones.
    """
    if doc_type not in {"ine", "comprobante_domicilio", "otro"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tipo de documento no válido. Usa: ine, comprobante_domicilio u otro.",
        )

    # Se valida que el cliente exista antes de escribir el archivo: si no,
    # quedaria un archivo huerfano en disco.
    try:
        await client_service.get_client(session, context.tenant_id, client_id)
    except client_service.ClientNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    content = await file.read()
    mime_type = file.content_type or "application/octet-stream"

    storage = get_storage()
    try:
        file_key = storage.save(
            context.tenant_id,
            client_id,
            doc_type,
            content,
            mime_type,
        )
    except InvalidFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    try:
        document = await client_service.add_document(
            session,
            context.tenant_id,
            client_id,
            doc_type=doc_type,
            file_key=file_key,
            mime_type=mime_type,
            size_bytes=len(content),
            uploaded_by=context.user.id,
        )
    except Exception:
        # Si falla el registro, se borra el archivo para no dejarlo huerfano.
        storage.delete(file_key)
        raise

    meta = request_meta(request)
    await audit_service.record(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user.id,
        action="client.document_upload",
        entity="client_document",
        entity_id=document.id,
        after={
            "client_id": str(client_id),
            "doc_type": doc_type,
            "mime_type": mime_type,
            "size_bytes": len(content),
        },
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        commit=True,
    )

    return DocumentRead.model_validate(document)


@router.get(
    "/{client_id}/documents/{document_id}",
    summary="Descargar un documento",
    description="Devuelve el archivo. Solo para usuarios de la misma financiera.",
    response_class=Response,
)
async def download_document(
    client_id: UUID,
    document_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> Response:
    """Descarga el contenido de un documento.

    Raises:
        HTTPException: 404 si el cliente o el documento no existen.
    """
    try:
        await client_service.get_client(session, context.tenant_id, client_id)
    except client_service.ClientNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    documents = await client_service.list_documents(session, context.tenant_id, client_id)
    document = next((doc for doc in documents if doc.id == document_id), None)

    if document is None:
        raise _not_found("El documento no existe.")

    storage = get_storage()
    try:
        content = storage.read(document.file_key)
    except StorageError as exc:
        raise _not_found(str(exc)) from exc

    extension = document.mime_type.split("/")[-1]
    filename = f"{document.doc_type}-{document.id.hex[:8]}.{extension}"

    return Response(
        content=content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(len(content)),
            # Los documentos son datos personales: no se cachean.
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/{client_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un documento",
)
async def delete_document(
    client_id: UUID,
    document_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> None:
    """Borra el documento del almacenamiento y de la base.

    Raises:
        HTTPException: 404 si no existe.
    """
    try:
        await client_service.get_client(session, context.tenant_id, client_id)
    except client_service.ClientNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    try:
        file_key = await client_service.remove_document(
            session, context.tenant_id, client_id, document_id
        )
    except client_service.ClientNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    get_storage().delete(file_key)

    await audit_service.record(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user.id,
        action="client.document_delete",
        entity="client_document",
        entity_id=document_id,
        before={"client_id": str(client_id)},
        commit=True,
    )
