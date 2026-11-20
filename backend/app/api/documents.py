"""Gestión de documentos (solo administradores en esta fase).

En la fase 5 los usuarios normales podrán listar los documentos que tengan autorizados.
"""
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.deps import AdminUser, DbSession
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.document import Chunk, Document, DocumentStatus, FileType
from app.schemas.documents import ChunkRead, DocumentRead
from app.services.embeddings import Embedder, get_embedder
from app.services.ingestion import run_ingestion_job

router = APIRouter(prefix="/documents", tags=["documents"])

EXTENSIONS = {".pdf": FileType.PDF, ".docx": FileType.DOCX, ".txt": FileType.TXT}


def embedder_dependency() -> Embedder:
    try:
        return get_embedder()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


EmbedderDep = Annotated[Embedder, Depends(embedder_dependency)]
SessionFactory = Annotated[sessionmaker, Depends(get_session_factory)]


def _looks_like(file_type: FileType, head: bytes) -> bool:
    """Comprueba la firma del archivo (magic bytes): la extensión se puede falsear."""
    if file_type is FileType.PDF:
        return head.startswith(b"%PDF-")
    if file_type is FileType.DOCX:
        return head.startswith(b"PK\x03\x04")  # un .docx es un ZIP
    return b"\x00" not in head  # TXT: sin bytes nulos (no es binario)


async def _save_upload(upload: UploadFile, dest: Path, max_bytes: int) -> int:
    """Guarda el archivo en disco por bloques, cortando si supera el límite."""
    size = 0
    with dest.open("wb") as out:
        while block := await upload.read(1024 * 1024):
            size += len(block)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    f"El archivo supera {max_bytes // (1024 * 1024)} MB",
                )
            out.write(block)
    return size


def _get_document(db: DbSession, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    return document


@router.post("", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    admin: AdminUser,
    db: DbSession,
    background: BackgroundTasks,
    embedder: EmbedderDep,
    session_factory: SessionFactory,
    file: Annotated[UploadFile, File(description="PDF, DOCX o TXT")],
    title: Annotated[str | None, Form(max_length=255)] = None,
) -> Document:
    """Sube un documento y lanza su procesamiento en segundo plano.

    Devuelve 202 Accepted: el documento queda en `pending`; consulta
    `GET /documents/{id}` hasta que esté `ready` (o `failed`).
    """
    settings = get_settings()
    original_name = Path(file.filename or "documento").name  # evita rutas tipo ../../
    file_type = EXTENSIONS.get(Path(original_name).suffix.lower())
    if file_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Formato no soportado. Usa PDF, DOCX o TXT."
        )

    head = await file.read(8192)
    if not _looks_like(file_type, head):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"El contenido no corresponde a un archivo {file_type.value.upper()}",
        )
    await file.seek(0)

    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    # Nombre en disco aleatorio: nunca usamos el nombre que manda el cliente
    stored_filename = f"{uuid.uuid4().hex}.{file_type.value}"
    size = await _save_upload(
        file, settings.storage_dir / stored_filename, settings.max_upload_mb * 1024 * 1024
    )

    document = Document(
        title=(title or Path(original_name).stem).strip()[:255],
        original_filename=original_name[:255],
        stored_filename=stored_filename,
        file_type=file_type,
        size_bytes=size,
        status=DocumentStatus.PENDING,
        uploaded_by_id=admin.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background.add_task(run_ingestion_job, document.id, session_factory, embedder)
    return document


@router.get("", response_model=list[DocumentRead])
def list_documents(_: AdminUser, db: DbSession) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.created_at.desc(), Document.id.desc())))


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, _: AdminUser, db: DbSession) -> Document:
    return _get_document(db, document_id)


@router.get("/{document_id}/chunks", response_model=list[ChunkRead])
def list_chunks(
    document_id: int,
    _: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Chunk]:
    """Útil para inspeccionar cómo se ha troceado un documento."""
    _get_document(db, document_id)
    return list(
        db.scalars(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/{document_id}/reprocess", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
def reprocess_document(
    document_id: int,
    _: AdminUser,
    db: DbSession,
    background: BackgroundTasks,
    embedder: EmbedderDep,
    session_factory: SessionFactory,
) -> Document:
    document = _get_document(db, document_id)
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "El documento ya se está procesando")
    document.status = DocumentStatus.PENDING
    db.commit()
    background.add_task(run_ingestion_job, document.id, session_factory, embedder)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, _: AdminUser, db: DbSession) -> None:
    document = _get_document(db, document_id)
    path = get_settings().storage_dir / document.stored_filename
    db.delete(document)  # los chunks se borran en cascada
    db.commit()
    path.unlink(missing_ok=True)
