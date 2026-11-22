from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus, FileType, Visibility
from app.schemas.groups import GroupBrief


class DocumentRead(BaseModel):
    """Vista completa (administradores)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    original_filename: str
    file_type: FileType
    size_bytes: int
    status: DocumentStatus
    error: str | None
    num_pages: int | None
    num_chunks: int | None
    uploaded_by_id: int | None
    created_at: datetime
    processed_at: datetime | None
    visibility: Visibility
    groups: list[GroupBrief]


class DocumentSummary(BaseModel):
    """Vista para usuarios: qué documentos pueden consultar, sin detalles internos."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    file_type: FileType
    num_pages: int | None
    processed_at: datetime | None


class ChunkRead(BaseModel):
    """Chunk sin el embedding (1536 números no aportan nada al leerlo)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    page_number: int
    token_count: int
    content: str
