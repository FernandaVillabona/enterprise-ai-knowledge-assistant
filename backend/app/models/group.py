"""Grupos (departamentos, equipos…) para el control de acceso a documentos.

Modelo de permisos (RBAC sencillo basado en grupos):
- Un usuario pertenece a 0..n grupos.
- Un documento es `public` (lo ve cualquier usuario autenticado) o `restricted`
  (solo lo ven los miembros de alguno de sus grupos).
- Los administradores ven todo.

Las tablas de asociación (muchos a muchos) no necesitan clase propia: basta con Table.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True),
)

document_groups = Table(
    "document_groups",
    Base.metadata,
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(  # noqa: F821
        secondary=user_groups, back_populates="groups", order_by="User.email"
    )
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        secondary=document_groups, back_populates="groups"
    )
