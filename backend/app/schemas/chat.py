from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat import MessageRole


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class SourceRead(BaseModel):
    n: int
    chunk_id: int
    document_id: int
    document_title: str
    page_number: int
    content: str
    score: float
    similarity: float | None
    cited: bool


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    search_query: str | None = None
    sources: list[SourceRead] | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ChatTurn(BaseModel):
    """Respuesta al enviar un mensaje: la pregunta guardada y la respuesta del asistente."""

    conversation_id: int
    user_message: MessageRead
    assistant_message: MessageRead
