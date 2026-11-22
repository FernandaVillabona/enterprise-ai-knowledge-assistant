"""Conversaciones y chat RAG. Cada usuario solo ve sus propias conversaciones."""
import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, LLMDep, RetrieverDep
from app.models.chat import Conversation, Message, MessageRole
from app.models.user import User
from app.schemas.chat import (
    ChatTurn,
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    MessageCreate,
)
from app.services.llm import ChatMessage
from app.services.permissions import accessible_document_ids
from app.services.rag import answer_question

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["chat"])

DEFAULT_TITLE = "Nueva conversación"


def _source_document_ids(messages: list[Message]) -> set[int]:
    return {s["document_id"] for m in messages for s in (m.sources or [])}


def _history_for_llm(db: DbSession, user: User, messages: list[Message]) -> list[ChatMessage]:
    """Historial que se envía al modelo.

    Si el usuario ha perdido acceso a un documento, las respuestas anteriores que lo
    citaban contienen información que ya no debe ver: no se reenvían al modelo.
    """
    allowed = accessible_document_ids(db, user, _source_document_ids(messages))
    history = []
    for m in messages:
        cited_docs = {s["document_id"] for s in (m.sources or []) if s.get("cited")}
        if m.role == MessageRole.ASSISTANT and not cited_docs <= allowed:
            continue
        history.append(ChatMessage(m.role.value, m.content))
    return history


def _get_own_conversation(db: DbSession, user: User, conversation_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    # 404 (y no 403) si es de otro usuario: no revelamos que existe
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada")
    return conversation


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(data: ConversationCreate, user: CurrentUser, db: DbSession) -> Conversation:
    conversation = Conversation(user_id=user.id, title=data.title or DEFAULT_TITLE)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationRead])
def list_conversations(user: CurrentUser, db: DbSession) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        )
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int, user: CurrentUser, db: DbSession) -> ConversationDetail:
    """Conversación con sus mensajes.

    Las fuentes guardadas incluyen el texto de los fragmentos. Si desde entonces el
    usuario perdió acceso a un documento (o se borró), esas fuentes se omiten: los
    permisos se evalúan al leer, no solo al preguntar.
    """
    conversation = _get_own_conversation(db, user, conversation_id)
    detail = ConversationDetail.model_validate(conversation)
    allowed = accessible_document_ids(db, user, _source_document_ids(conversation.messages))
    for message in detail.messages:
        if message.sources is not None:
            message.sources = [s for s in message.sources if s.document_id in allowed]
    return detail


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, user: CurrentUser, db: DbSession) -> None:
    db.delete(_get_own_conversation(db, user, conversation_id))
    db.commit()


@router.post("/{conversation_id}/messages", response_model=ChatTurn)
def send_message(
    conversation_id: int,
    data: MessageCreate,
    user: CurrentUser,
    db: DbSession,
    llm: LLMDep,
    retrieve: RetrieverDep,
) -> ChatTurn:
    """Envía una pregunta y devuelve la respuesta del asistente con sus fuentes.

    En `sources`, `cited=true` marca las fuentes que el modelo citó realmente.
    """
    conversation = _get_own_conversation(db, user, conversation_id)
    history = _history_for_llm(db, user, conversation.messages)

    try:
        result = answer_question(llm, retrieve, data.content, history)
    except Exception:
        logger.exception("Error generando respuesta en la conversación %s", conversation_id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "No se pudo generar la respuesta. Inténtalo de nuevo."
        )
    if result.invalid_citations:
        logger.warning(
            "Citas a fuentes inexistentes eliminadas %s (conversación %s)",
            result.invalid_citations,
            conversation_id,
        )

    user_message = Message(conversation_id=conversation.id, role=MessageRole.USER, content=data.content)
    assistant_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=result.answer,
        search_query=result.search_query,
        sources=[asdict(s) for s in result.sources],
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
    )
    # La primera pregunta da título a la conversación
    if conversation.title == DEFAULT_TITLE and not conversation.messages:
        conversation.title = data.content[:80] + ("…" if len(data.content) > 80 else "")
    conversation.updated_at = func.now()  # para ordenar la lista por actividad reciente
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)

    return ChatTurn(
        conversation_id=conversation.id,
        user_message=user_message,
        assistant_message=assistant_message,
    )
