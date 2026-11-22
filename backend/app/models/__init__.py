"""Importa aquí todos los modelos para que Alembic los detecte vía Base.metadata."""
from app.models.chat import Conversation, Message, MessageRole
from app.models.document import Chunk, Document, DocumentStatus, FileType, Visibility
from app.models.group import Group, document_groups, user_groups
from app.models.user import User, UserRole

__all__ = [
    "Chunk",
    "Conversation",
    "Document",
    "DocumentStatus",
    "FileType",
    "Group",
    "Message",
    "MessageRole",
    "User",
    "UserRole",
    "Visibility",
    "document_groups",
    "user_groups",
]
