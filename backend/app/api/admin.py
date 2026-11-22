"""Calidad del asistente: métricas agregadas y cola de revisión (solo administradores)."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession
from app.models.chat import Conversation, Message, MessageRole
from app.models.user import User
from app.schemas.admin import FlaggedMessage, QualityMetrics
from app.services.rag import NO_INFO_ANSWER

router = APIRouter(prefix="/admin", tags=["admin: quality"])


def _ratio(part: int, total: int) -> float | None:
    return round(part / total, 3) if total else None


@router.get("/metrics", response_model=QualityMetrics)
def quality_metrics(
    _: AdminUser, db: DbSession, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> QualityMetrics:
    """Métricas de calidad de los últimos `days` días, calculadas en una sola consulta SQL."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    m = Message
    row = db.execute(
        select(
            func.count().label("answers"),
            func.count().filter(m.content == NO_INFO_ANSWER).label("no_info"),
            func.count(m.faithfulness_score).label("evaluated"),
            func.avg(m.faithfulness_score).label("avg_faithfulness"),
            func.count().filter(m.faithfulness_score < 1).label("hallucinated"),
            func.count().filter(m.flagged.is_(True)).label("flagged"),
            func.count().filter(m.feedback_rating == 1).label("positive"),
            func.count().filter(m.feedback_rating == -1).label("negative"),
            func.avg(m.latency_ms).label("avg_latency"),
            func.coalesce(func.sum(m.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(m.completion_tokens), 0).label("completion_tokens"),
        ).where(m.role == MessageRole.ASSISTANT, m.created_at >= since)
    ).one()

    return QualityMetrics(
        since=since,
        answers=row.answers,
        no_info_answers=row.no_info,
        no_info_rate=_ratio(row.no_info, row.answers),
        evaluated=row.evaluated,
        avg_faithfulness=round(float(row.avg_faithfulness), 3) if row.avg_faithfulness is not None else None,
        hallucination_rate=_ratio(row.hallucinated, row.evaluated),
        flagged=row.flagged,
        feedback_positive=row.positive,
        feedback_negative=row.negative,
        avg_latency_ms=round(float(row.avg_latency), 1) if row.avg_latency is not None else None,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
    )


@router.get("/flagged", response_model=list[FlaggedMessage])
def flagged_messages(
    _: AdminUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[FlaggedMessage]:
    """Respuestas marcadas (juez, citas inválidas, sin citas o 👎), más recientes primero."""
    # La pregunta es el mensaje de usuario inmediatamente anterior en la misma conversación:
    # una subconsulta correlacionada con el alias `answer` de la consulta principal.
    answer = Message.__table__.alias("answer")
    previous_question = (
        select(Message.content)
        .where(
            Message.conversation_id == answer.c.conversation_id,
            Message.role == MessageRole.USER,
            Message.id < answer.c.id,
        )
        .order_by(Message.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = db.execute(
        select(answer, User.email, previous_question.label("question"))
        .join(Conversation, Conversation.id == answer.c.conversation_id)
        .join(User, User.id == Conversation.user_id)
        .where(answer.c.flagged.is_(True), answer.c.role == MessageRole.ASSISTANT)
        .order_by(answer.c.created_at.desc(), answer.c.id.desc())
        .limit(limit)
    ).all()
    return [
        FlaggedMessage(
            message_id=r.id,
            conversation_id=r.conversation_id,
            user_email=r.email,
            question=r.question,
            answer=r.content,
            evaluation=r.evaluation,
            faithfulness_score=r.faithfulness_score,
            feedback_rating=r.feedback_rating,
            feedback_comment=r.feedback_comment,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/flagged/{message_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
def resolve_flag(message_id: int, _: AdminUser, db: DbSession) -> None:
    """Marca una respuesta como revisada (sale de la cola)."""
    message = db.get(Message, message_id)
    if message is None or not message.flagged:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay ninguna respuesta marcada con ese id")
    message.flagged = False
    db.commit()
