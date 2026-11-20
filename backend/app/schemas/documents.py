from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus, FileType


class DocumentRead(BaseModel):
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


class ChunkRead(BaseModel):
    """Chunk sin el embedding (1536 números no aportan nada al leerlo)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    page_number: int
    token_count: int
    content: str
