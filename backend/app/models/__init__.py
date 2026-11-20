"""Importa aquí todos los modelos para que Alembic los detecte vía Base.metadata."""
from app.models.document import Chunk, Document, DocumentStatus, FileType
from app.models.user import User, UserRole

__all__ = ["Chunk", "Document", "DocumentStatus", "FileType", "User", "UserRole"]
