"""Importa aquí todos los modelos para que Alembic los detecte vía Base.metadata."""
from app.models.user import User, UserRole

__all__ = ["User", "UserRole"]
