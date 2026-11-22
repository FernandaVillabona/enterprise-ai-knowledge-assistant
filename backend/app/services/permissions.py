"""Control de acceso a documentos.

Regla de oro del RAG empresarial: **el filtro de permisos va en la consulta de
recuperación**, no después. Si recuperáramos todo y filtráramos al final (o, peor,
le pidiéramos al LLM que «no use» ciertos documentos), un fragmento confidencial
podría llegar al prompt y filtrarse en la respuesta. Aquí devolvemos una condición
SQL que se añade al WHERE de cualquier consulta sobre `documents`, de modo que lo
no autorizado nunca sale de la base de datos.
"""
from sqlalchemy import ColumnElement, and_, exists, or_, select, true
from sqlalchemy.orm import Session

from app.models.document import Document, Visibility
from app.models.group import document_groups, user_groups
from app.models.user import User, UserRole


def document_access_condition(user: User) -> ColumnElement[bool]:
    """Condición SQL: «el documento es visible para `user`».

        visibility = 'public'
        OR EXISTS (un grupo del documento al que pertenece el usuario)

    Los administradores ven todo.
    """
    if user.role == UserRole.ADMIN:
        return true()

    shares_a_group = exists(
        select(1)
        .select_from(document_groups)
        .join(user_groups, user_groups.c.group_id == document_groups.c.group_id)
        .where(
            and_(
                document_groups.c.document_id == Document.id,
                user_groups.c.user_id == user.id,
            )
        )
    )
    return or_(Document.visibility == Visibility.PUBLIC, shares_a_group)


def can_access_document(db: Session, user: User, document_id: int) -> bool:
    return bool(
        db.scalar(
            select(Document.id).where(Document.id == document_id, document_access_condition(user))
        )
    )


def accessible_document_ids(db: Session, user: User, candidate_ids: set[int]) -> set[int]:
    """De un conjunto de documentos, cuáles puede ver el usuario (una sola consulta)."""
    if not candidate_ids:
        return set()
    return set(
        db.scalars(
            select(Document.id).where(Document.id.in_(candidate_ids), document_access_condition(user))
        )
    )
