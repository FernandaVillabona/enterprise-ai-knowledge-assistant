"""Pipeline de ingesta: archivo → páginas → chunks → embeddings → base de datos.

Se ejecuta en segundo plano (BackgroundTasks de FastAPI) para que la subida
responda al instante; el frontend consulta `status` para saber cuándo está listo.

Nota de aprendizaje: BackgroundTasks corre en el mismo proceso que la API. Si el
servidor se reinicia a mitad, el documento se queda en `processing`. En producción
se usaría una cola (Celery, RQ, arq) con reintentos; aquí basta con el endpoint
`/reprocess` para relanzarlo.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.document import Chunk, Document, DocumentStatus
from app.services.chunking import chunk_pages
from app.services.embeddings import Embedder
from app.services.extraction import extract_pages

logger = logging.getLogger(__name__)


def build_embedding_input(title: str, content: str) -> str:
    """Texto que se convierte en embedding.

    Anteponemos el título del documento: un fragmento que dice «son 23 días hábiles»
    no menciona «vacaciones», pero con el título «Política de vacaciones» delante su
    embedding queda mucho más cerca de la pregunta del usuario.
    """
    return f"{title}\n\n{content}"


def ingest_document(db: Session, document: Document, embedder: Embedder) -> None:
    settings = get_settings()
    document.status = DocumentStatus.PROCESSING
    document.error = None
    db.commit()

    try:
        path = settings.storage_dir / document.stored_filename
        pages = extract_pages(path, document.file_type)
        chunks = chunk_pages(
            pages,
            max_tokens=settings.chunk_size_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        vectors = embedder.embed([build_embedding_input(document.title, c.content) for c in chunks])

        # Re-procesar = reemplazar los chunks anteriores
        db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        db.add_all(
            Chunk(
                document_id=document.id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                content=c.content,
                token_count=c.token_count,
                embedding=v,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        document.num_pages = len(pages)
        document.num_chunks = len(chunks)
        document.status = DocumentStatus.READY
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Documento %s procesado: %s chunks", document.id, len(chunks))
    except Exception as exc:
        db.rollback()
        logger.exception("Error procesando documento %s", document.id)
        document.status = DocumentStatus.FAILED
        document.error = str(exc)[:1000]
        db.commit()


def run_ingestion_job(document_id: int, session_factory: sessionmaker, embedder: Embedder) -> None:
    """Punto de entrada de la tarea en segundo plano: abre su propia sesión de BD."""
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("Documento %s ya no existe; se omite la ingesta", document_id)
            return
        ingest_document(db, document, embedder)
