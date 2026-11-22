"""Evaluación de respuestas: detección de alucinaciones.

Dos tipos de comprobaciones:

1. Deterministas (gratis, instantáneas, sin falsos positivos):
   - citas a fuentes inexistentes (ya detectadas en services/rag.py);
   - respuesta sin ninguna cita aunque había fuentes (sospechosa: ¿de dónde sale?).

2. LLM-as-judge (fidelidad / *faithfulness*): otro LLM descompone la respuesta en
   afirmaciones atómicas y comprueba si cada una está respaldada por las fuentes.
       fidelidad = afirmaciones respaldadas / afirmaciones totales
   Una afirmación no respaldada es, por definición, una alucinación respecto al
   contexto, aunque sea verdad en el mundo real: el asistente solo debe decir lo
   que dicen los documentos.

Limitaciones a tener en cuenta: el juez también es un LLM y puede equivocarse. Por eso
lo combinamos con checks deterministas, con el feedback de usuarios y con un conjunto
de preguntas de referencia revisado por personas (ver services/eval_runner.py).
"""
import json
import logging
import re
from dataclasses import asdict, dataclass, field

from app.services.llm import ChatLLM, ChatMessage
from app.services.rag import NO_INFO_ANSWER, extract_citations

logger = logging.getLogger(__name__)

FAITHFULNESS_PROMPT = """Eres un evaluador estricto de un sistema RAG. Recibes unas FUENTES \
numeradas y una RESPUESTA generada a partir de ellas.

Tarea:
1. Divide la RESPUESTA en afirmaciones atómicas verificables (hechos, cifras, condiciones). \
Ignora frases de cortesía y las referencias a fuentes como [1].
2. Para cada afirmación decide si está RESPALDADA por las fuentes: la información debe \
aparecer explícitamente o deducirse de forma directa. Si añade datos, cifras o matices que \
no están, NO está respaldada. No uses conocimiento externo.
3. Indica qué fuentes la respaldan.

Responde SOLO con JSON con este formato:
{"claims": [{"claim": "texto", "supported": true, "sources": [1]}]}"""

CORRECTNESS_PROMPT = """Eres un evaluador. Compara la RESPUESTA de un asistente con la \
RESPUESTA DE REFERENCIA escrita por una persona para la misma PREGUNTA.

Puntúa:
- 1: contiene los hechos clave de la referencia y no los contradice.
- 0.5: parcialmente correcta (le faltan hechos clave o es imprecisa).
- 0: incorrecta, la contradice o no responde.

Responde SOLO con JSON: {"score": 1, "reason": "explicación breve"}"""


class Verdict:
    SUPPORTED = "supported"  # todas las afirmaciones respaldadas
    PARTIAL = "partially_supported"
    UNSUPPORTED = "unsupported"
    NO_ANSWER = "no_answer"  # el asistente dijo que no hay información: nada que verificar
    ERROR = "error"  # el juez falló o devolvió algo ilegible
    PENDING = "pending"  # el juez aún no ha terminado (se ejecuta en segundo plano)
    NOT_EVALUATED = "not_evaluated"  # evaluación automática desactivada


@dataclass
class Claim:
    claim: str
    supported: bool
    sources: list[int] = field(default_factory=list)


@dataclass
class Evaluation:
    verdict: str
    faithfulness: float | None  # 0..1; None si no aplica
    claims: list[Claim] = field(default_factory=list)
    invalid_citations: list[int] = field(default_factory=list)
    uncited: bool = False  # respondió sin citar nada habiendo fuentes
    judge_model: str | None = None
    error: str | None = None

    def is_flagged(self, threshold: float) -> bool:
        """¿Debe revisarla una persona?"""
        if self.verdict in (Verdict.ERROR, Verdict.PENDING, Verdict.NOT_EVALUATED):
            # Sin veredicto del juez solo cuentan los checks deterministas
            return bool(self.invalid_citations) or self.uncited  # un fallo del juez no es culpa de la respuesta; se registra aparte
        return (
            bool(self.invalid_citations)
            or self.uncited
            or (self.faithfulness is not None and self.faithfulness < threshold)
        )

    def to_dict(self) -> dict:
        return asdict(self)


def parse_json_object(text: str) -> dict:
    """Extrae el objeto JSON de la salida del modelo (tolera ```json ... ``` alrededor)."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No hay un objeto JSON en la respuesta del juez")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("El JSON del juez no es un objeto")
    return data


def _format_sources(sources: list[dict]) -> str:
    return "\n\n".join(
        f"[{s['n']}] {s['document_title']} (pág. {s['page_number']}):\n{s['content']}" for s in sources
    )


def evaluate_faithfulness(
    judge: ChatLLM,
    answer: str,
    sources: list[dict],
    invalid_citations: list[int] | None = None,
) -> Evaluation:
    """Evalúa una respuesta frente a las fuentes que se le dieron al modelo.

    `sources` usa el formato guardado en Message.sources (dicts con n, document_title,
    page_number, content…).
    """
    invalid = list(invalid_citations or [])
    if answer.strip() == NO_INFO_ANSWER or not sources:
        return Evaluation(Verdict.NO_ANSWER, None, invalid_citations=invalid)

    uncited = not extract_citations(answer)
    try:
        result = judge.complete(
            [
                ChatMessage("system", FAITHFULNESS_PROMPT),
                ChatMessage("user", f"FUENTES:\n{_format_sources(sources)}\n\nRESPUESTA:\n{answer}"),
            ],
            max_tokens=1200,
            json_mode=True,
        )
        raw_claims = parse_json_object(result.text).get("claims", [])
        claims = [
            Claim(
                claim=str(c.get("claim", "")),
                supported=bool(c.get("supported", False)),
                sources=[int(n) for n in c.get("sources", []) if str(n).isdigit()],
            )
            for c in raw_claims
            if isinstance(c, dict)
        ]
    except Exception as exc:
        logger.warning("Fallo del juez de fidelidad: %s", exc)
        return Evaluation(Verdict.ERROR, None, invalid_citations=invalid, uncited=uncited, error=str(exc)[:500])

    if not claims:
        # Nada verificable (p. ej. "Depende de tu contrato"): ni premio ni castigo
        return Evaluation(Verdict.SUPPORTED, None, [], invalid, uncited, result.model)

    score = sum(c.supported for c in claims) / len(claims)
    if score == 1:
        verdict = Verdict.SUPPORTED
    elif score >= 0.5:
        verdict = Verdict.PARTIAL
    else:
        verdict = Verdict.UNSUPPORTED
    return Evaluation(verdict, round(score, 3), claims, invalid, uncited, result.model)


def evaluate_correctness(judge: ChatLLM, question: str, answer: str, reference: str) -> tuple[float, str]:
    """Compara con una respuesta de referencia (solo en evaluación offline)."""
    result = judge.complete(
        [
            ChatMessage("system", CORRECTNESS_PROMPT),
            ChatMessage(
                "user",
                f"PREGUNTA:\n{question}\n\nRESPUESTA DE REFERENCIA:\n{reference}\n\nRESPUESTA:\n{answer}",
            ),
        ],
        max_tokens=300,
        json_mode=True,
    )
    data = parse_json_object(result.text)
    score = float(data.get("score", 0))
    return min(max(score, 0.0), 1.0), str(data.get("reason", ""))


# ---------- Evaluación online (tras cada respuesta del chat) ----------

def initial_evaluation(answer: str, sources: list[dict], invalid_citations: list[int], judged: bool) -> Evaluation:
    """Checks deterministas, al instante. Si habrá juez, el veredicto queda `pending`."""
    if answer.strip() == NO_INFO_ANSWER or not sources:
        return Evaluation(Verdict.NO_ANSWER, None, invalid_citations=invalid_citations)
    return Evaluation(
        Verdict.PENDING if judged else Verdict.NOT_EVALUATED,
        None,
        invalid_citations=invalid_citations,
        uncited=not extract_citations(answer),
    )


def run_evaluation_job(message_id: int, session_factory, judge: ChatLLM) -> None:
    """Tarea en segundo plano: evalúa la fidelidad de un mensaje del asistente y lo guarda.

    Va en segundo plano porque es una segunda llamada al LLM: el usuario recibe la
    respuesta sin esperar y el veredicto aparece después en el historial.
    """
    from app.core.config import get_settings
    from app.models.chat import Message

    with session_factory() as db:
        message = db.get(Message, message_id)
        if message is None:
            return
        previous = message.evaluation or {}
        evaluation = evaluate_faithfulness(
            judge, message.content, message.sources or [], previous.get("invalid_citations", [])
        )
        message.evaluation = evaluation.to_dict()
        message.faithfulness_score = evaluation.faithfulness
        message.flagged = evaluation.is_flagged(get_settings().eval_flag_threshold)
        db.commit()
        if message.flagged:
            logger.warning("Respuesta %s marcada para revisión: %s", message_id, evaluation.verdict)
