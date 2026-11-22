from datetime import datetime

from pydantic import BaseModel


class QualityMetrics(BaseModel):
    since: datetime
    answers: int  # respuestas del asistente en el periodo
    no_info_answers: int  # «no he encontrado información»
    no_info_rate: float | None
    evaluated: int  # con puntuación de fidelidad del juez
    avg_faithfulness: float | None
    hallucination_rate: float | None  # evaluadas con alguna afirmación no respaldada
    flagged: int  # pendientes de revisión
    feedback_positive: int
    feedback_negative: int
    avg_latency_ms: float | None
    prompt_tokens: int
    completion_tokens: int


class FlaggedMessage(BaseModel):
    message_id: int
    conversation_id: int
    user_email: str
    question: str | None
    answer: str
    evaluation: dict | None
    faithfulness_score: float | None
    feedback_rating: int | None
    feedback_comment: str | None
    created_at: datetime
