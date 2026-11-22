"""Evaluación offline contra un conjunto de preguntas de referencia («golden dataset»).

¿Para qué? Para cambiar el sistema (prompt, tamaño de chunk, modelo, top_k…) y saber
con números si mejora o empeora, en lugar de «a mí me parece que responde mejor».

Cada caso del dataset (eval/golden_dataset.jsonl) indica la pregunta, qué usuario la
hace (para probar permisos), la respuesta esperada (o null si NO debe responder) y en
qué documentos/páginas está la respuesta. Medimos:

Recuperación (¿encontramos el contexto correcto?)
  - hit_rate: % de preguntas en las que algún documento esperado está entre los recuperados.
  - mrr: Mean Reciprocal Rank; 1 si el documento correcto sale el primero, 0.5 si segundo…
  - page_hit_rate: igual, pero exigiendo además la página correcta.
Generación (¿la respuesta es buena?)
  - faithfulness: fidelidad media a las fuentes (juez LLM); 1 = sin alucinaciones.
  - hallucination_rate: % de respuestas con alguna afirmación no respaldada o cita inválida.
  - correctness: parecido con la respuesta de referencia (juez LLM, 0 / 0.5 / 1).
  - refusal_accuracy: % de casos en que acierta al responder o al decir «no hay información».
"""
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.services.evaluation import evaluate_correctness, evaluate_faithfulness
from app.services.llm import ChatLLM
from app.services.rag import NO_INFO_ANSWER, Retriever, answer_question


@dataclass
class EvalCase:
    id: str
    question: str
    as_user: str
    expected_answer: str | None
    expected_documents: list[str] = field(default_factory=list)
    expected_pages: list[int] = field(default_factory=list)
    notes: str | None = None

    @property
    def should_answer(self) -> bool:
        return self.expected_answer is not None


@dataclass
class CaseResult:
    id: str
    question: str
    as_user: str
    should_answer: bool
    answered: bool = False
    answer: str = ""
    search_query: str = ""
    retrieved: list[dict] = field(default_factory=list)  # [{title, page, cited}]
    retrieval_hit: bool | None = None
    reciprocal_rank: float | None = None
    page_hit: bool | None = None
    faithfulness: float | None = None
    verdict: str | None = None
    unsupported_claims: list[str] = field(default_factory=list)
    invalid_citations: list[int] = field(default_factory=list)
    correctness: float | None = None
    correctness_reason: str | None = None
    latency_ms: int = 0
    tokens: int = 0
    error: str | None = None

    @property
    def refusal_correct(self) -> bool:
        return self.answered == self.should_answer

    @property
    def hallucinated(self) -> bool:
        return bool(self.invalid_citations) or (self.faithfulness is not None and self.faithfulness < 1)


def load_dataset(path: Path) -> list[EvalCase]:
    cases = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(EvalCase(**json.loads(line)))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"{path.name}:{n}: caso inválido ({exc})") from exc
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids de caso repetidos en el dataset")
    return cases


def _retrieval_metrics(case: EvalCase, retrieved: list[dict]) -> tuple[bool | None, float | None, bool | None]:
    if not case.expected_documents:
        return None, None, None
    titles = [r["title"] for r in retrieved]
    rank = next((i for i, t in enumerate(titles, start=1) if t in case.expected_documents), None)
    page_hit = None
    if case.expected_pages:
        page_hit = any(
            r["title"] in case.expected_documents and r["page"] in case.expected_pages for r in retrieved
        )
    return rank is not None, (1 / rank if rank else 0.0), page_hit


def run_case(
    case: EvalCase, llm: ChatLLM, judge: ChatLLM, retriever_for: Callable[[str], Retriever]
) -> CaseResult:
    result = CaseResult(case.id, case.question, case.as_user, case.should_answer)
    try:
        rag = answer_question(llm, retriever_for(case.as_user), case.question)
    except Exception as exc:  # un caso roto no debe tumbar toda la evaluación
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    sources = [asdict(s) for s in rag.sources]
    result.answer = rag.answer
    result.search_query = rag.search_query
    result.answered = rag.answer.strip() != NO_INFO_ANSWER
    result.retrieved = [{"title": s.document_title, "page": s.page_number, "cited": s.cited} for s in rag.sources]
    result.invalid_citations = rag.invalid_citations
    result.latency_ms = rag.latency_ms
    result.tokens = rag.prompt_tokens + rag.completion_tokens
    result.retrieval_hit, result.reciprocal_rank, result.page_hit = _retrieval_metrics(case, result.retrieved)

    if result.answered:
        evaluation = evaluate_faithfulness(judge, rag.answer, sources, rag.invalid_citations)
        result.faithfulness = evaluation.faithfulness
        result.verdict = evaluation.verdict
        result.unsupported_claims = [c.claim for c in evaluation.claims if not c.supported]
        if evaluation.error:
            result.error = f"juez: {evaluation.error}"
    if case.should_answer:
        if result.answered:
            try:
                result.correctness, result.correctness_reason = evaluate_correctness(
                    judge, case.question, rag.answer, case.expected_answer
                )
            except Exception as exc:
                result.error = f"juez de corrección: {exc}"
        else:
            result.correctness, result.correctness_reason = 0.0, "No respondió y debía hacerlo"
    return result


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summarize(results: list[CaseResult]) -> dict:
    answered = [r for r in results if r.answered]
    with_docs = [r for r in results if r.retrieval_hit is not None]
    with_pages = [r for r in results if r.page_hit is not None]
    faithfulness = [r.faithfulness for r in answered if r.faithfulness is not None]
    correctness = [r.correctness for r in results if r.correctness is not None]
    return {
        "cases": len(results),
        "errors": sum(r.error is not None for r in results),
        "hit_rate": _mean([float(r.retrieval_hit) for r in with_docs]),
        "mrr": _mean([r.reciprocal_rank for r in with_docs]),
        "page_hit_rate": _mean([float(r.page_hit) for r in with_pages]),
        "faithfulness": _mean(faithfulness),
        "hallucination_rate": _mean([float(r.hallucinated) for r in answered]),
        "correctness": _mean(correctness),
        "refusal_accuracy": _mean([float(r.refusal_correct) for r in results]),
        "avg_latency_ms": _mean([float(r.latency_ms) for r in results if not r.error]),
        "total_tokens": sum(r.tokens for r in results),
    }


def _fmt(value: float | None, pct: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f} %" if pct else f"{value:.3f}"


def render_markdown(summary: dict, results: list[CaseResult], title: str = "Evaluación RAG") -> str:
    lines = [
        f"# {title}",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Casos | {summary['cases']} (errores: {summary['errors']}) |",
        f"| Hit rate (recuperación) | {_fmt(summary['hit_rate'])} |",
        f"| MRR | {_fmt(summary['mrr'], pct=False)} |",
        f"| Página correcta | {_fmt(summary['page_hit_rate'])} |",
        f"| Fidelidad media | {_fmt(summary['faithfulness'])} |",
        f"| Tasa de alucinación | {_fmt(summary['hallucination_rate'])} |",
        f"| Corrección vs. referencia | {_fmt(summary['correctness'])} |",
        f"| Acierto responder / rechazar | {_fmt(summary['refusal_accuracy'])} |",
        f"| Latencia media | {summary['avg_latency_ms'] or '—'} ms |",
        f"| Tokens totales | {summary['total_tokens']} |",
        "",
        "## Casos",
        "",
        "| Caso | Usuario | Recuperó | Fidelidad | Corrección | Resp./rech. | Notas |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        notes = r.error or "; ".join(f"No respaldado: {c}" for c in r.unsupported_claims)
        lines.append(
            f"| {r.id} | {r.as_user} | {'✅' if r.retrieval_hit else ('—' if r.retrieval_hit is None else '❌')} "
            f"| {_fmt(r.faithfulness)} | {_fmt(r.correctness)} | {'✅' if r.refusal_correct else '❌'} "
            f"| {notes.replace('|', '/')[:200]} |"
        )
    return "\n".join(lines) + "\n"


def results_to_json(summary: dict, results: list[CaseResult]) -> str:
    return json.dumps(
        {"summary": summary, "results": [asdict(r) | {"refusal_correct": r.refusal_correct} for r in results]},
        ensure_ascii=False,
        indent=2,
    )
