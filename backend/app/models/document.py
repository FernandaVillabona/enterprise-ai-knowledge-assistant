import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, literal_column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.session import Base

EMBEDDING_DIM = get_settings().embedding_dimensions

# Configuración de búsqueda de texto completo de PostgreSQL (stemming en español:
# «vacaciones», «vacación» → misma raíz). El índice GIN depende de este valor exacto:
# si lo cambias, crea una migración que regenere el índice.
FTS_CONFIG = literal_column("'spanish'::regconfig")


class DocumentStatus(str, enum.Enum):
    """Ciclo de vida de un documento: pending → processing → ready | failed."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class FileType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class Visibility(str, enum.Enum):
    """`public`: cualquier usuario autenticado. `restricted`: solo miembros de sus grupos."""

    PUBLIC = "public"
    RESTRICTED = "restricted"


def _values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    file_type: Mapped[FileType] = mapped_column(
        Enum(FileType, name="file_type", values_callable=_values)
    )
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=_values),
        default=DocumentStatus.PENDING,
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)
    num_pages: Mapped[int | None] = mapped_column(Integer, default=None)
    num_chunks: Mapped[int | None] = mapped_column(Integer, default=None)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Denegar por defecto: un documento nuevo solo lo ven los admins hasta que se le
    # asignen grupos o se haga público.
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="document_visibility", values_callable=_values),
        default=Visibility.RESTRICTED,
    )

    groups: Mapped[list["Group"]] = relationship(  # noqa: F821
        secondary="document_groups", back_populates="documents", order_by="Group.name"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chunk.chunk_index",
    )


class Chunk(Base):
    """Fragmento de un documento + su embedding.

    Es la unidad que recupera la búsqueda semántica. Guardamos `page_number`
    para poder citar «documento X, página Y» en las respuestas.
    """

    __tablename__ = "chunks"
    # Índices solo de PostgreSQL (.ddl_if): en los tests con SQLite se omiten.
    # Se declaran aquí (y no sueltos) para que queden ligados a la tabla: un Index cuya
    # única columna está dentro de una función no sabe a qué tabla pertenece.
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_chunks_content_fts",
            func.to_tsvector(FTS_CONFIG, literal_column("content")),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped[Document] = relationship(back_populates="chunks")


def chunk_tsvector():
    """Expresión tsvector del contenido. Debe ser IDÉNTICA a la del índice GIN para que
    PostgreSQL lo use (ver migración 0003)."""
    return func.to_tsvector(FTS_CONFIG, Chunk.content)
