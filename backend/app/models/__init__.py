"""Importa aquí todos los modelos para que Alembic los detecte vía Base.metadata."""
from app.models.chat import Conversation, Message, MessageRole
from app.models.document import Chunk, Document, DocumentStatus, FileType
from app.models.user import User, UserRole

__all__ = [
    "Chunk",
    "Conversation",
    "Document",
    "DocumentStatus",
    "FileType",
    "Message",
    "MessageRole",
    "User",
    "UserRole",
]
