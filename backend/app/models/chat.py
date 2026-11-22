import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# JSONB en PostgreSQL (binario, indexable); JSON genérico en SQLite (tests)
JsonType = JSON().with_variant(JSONB(), "postgresql")


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.id",
    )


class Message(Base):
    """Un turno del chat.

    En los mensajes del asistente guardamos también qué fuentes se recuperaron,
    cuáles se citaron y el consumo de tokens: es la materia prima para la
    evaluación de respuestas (fase 6) y para depurar por qué una respuesta salió mal.
    """

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("feedback_rating IN (-1, 1)", name="ck_messages_feedback_rating"),
        Index("ix_messages_flagged", "created_at", postgresql_where=text("flagged")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=lambda e: [m.value for m in e])
    )
    content: Mapped[str] = mapped_column(Text)
    # Solo asistente:
    search_query: Mapped[str | None] = mapped_column(Text)  # pregunta reescrita usada para buscar
    sources: Mapped[list[dict] | None] = mapped_column(JsonType)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # Evaluación (fase 6). `evaluation` guarda el detalle (veredicto, afirmaciones…);
    # `faithfulness_score` y `flagged` van en columnas propias para poder filtrar y agregar.
    evaluation: Mapped[dict | None] = mapped_column(JsonType)
    faithfulness_score: Mapped[float | None] = mapped_column(Float)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Feedback del usuario: 1 = útil, -1 = no útil
    feedback_rating: Mapped[int | None] = mapped_column(SmallInteger)
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
