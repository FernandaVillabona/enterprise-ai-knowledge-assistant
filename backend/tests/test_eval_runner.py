"""Tests del runner offline y de la coherencia del corpus demo con el golden dataset."""
import json

import pytest

from app.core.config import ROOT_DIR
from app.models.document import FileType
from app.services.eval_runner import EvalCase, load_dataset, render_markdown, run_case, summarize
from app.services.extraction import extract_pages
from app.services.llm import FakeLLM
from app.services.rag import NO_INFO_ANSWER, REWRITE_PROMPT
from app.services.search import SearchHit

DATASET = ROOT_DIR / "eval" / "golden_dataset.jsonl"
MANIFEST = ROOT_DIR / "samples" / "manifest.json"

VACATION = SearchHit(1, 1, "Política de vacaciones", 1, "Son 23 días hábiles.", 0.03, 0.9)
TRAVEL = SearchHit(2, 2, "Gastos de viaje", 2, "Dieta de 90 euros.", 0.02, 0.4)


def chat_llm(answer: str) -> FakeLLM:
    return FakeLLM(lambda m: "consulta" if m[0].content == REWRITE_PROMPT else answer)


def judge(faithful: bool = True, correctness: float = 1.0) -> FakeLLM:
    def respond(messages):
        if "RESPUESTA DE REFERENCIA" in messages[1].content:
            return json.dumps({"score": correctness, "reason": "r"})
        return json.dumps({"claims": [{"claim": "x", "supported": faithful, "sources": [1]}]})

    return FakeLLM(respond)


def retriever_returning(hits_by_user: dict[str, list[SearchHit]]):
    return lambda email: (lambda q, k: hits_by_user.get(email, [])[:k])


CASE = EvalCase("c1", "¿Vacaciones?", "eva@x", "23 días", ["Política de vacaciones"], [1])


def test_answered_case_metrics():
    r = run_case(CASE, chat_llm("Son 23 días [1]."), judge(), retriever_returning({"eva@x": [TRAVEL, VACATION]}))
    assert r.answered and r.refusal_correct
    assert r.retrieval_hit and r.reciprocal_rank == 0.5  # el documento correcto salió 2.º
    assert r.page_hit is True  # y en la página esperada (la página no depende de la posición)
    assert r.faithfulness == 1.0 and r.correctness == 1.0 and not r.hallucinated

    wrong_page = EvalCase("c1b", "¿Vacaciones?", "eva@x", "23 días", ["Política de vacaciones"], [3])
    r = run_case(wrong_page, chat_llm("Son 23 días [1]."), judge(), retriever_returning({"eva@x": [VACATION]}))
    assert r.retrieval_hit is True and r.page_hit is False


def test_case_that_must_refuse():
    case = EvalCase("c2", "¿Menú?", "eva@x", None)
    r = run_case(case, chat_llm("no debería llamarse"), judge(), retriever_returning({}))
    assert r.answer == NO_INFO_ANSWER and not r.answered and r.refusal_correct
    assert r.retrieval_hit is None and r.correctness is None


def test_missed_answer_and_hallucination_are_penalized():
    missed = run_case(CASE, chat_llm("x"), judge(), retriever_returning({}))
    assert not missed.refusal_correct and missed.correctness == 0.0 and missed.retrieval_hit is False

    halluc = run_case(CASE, chat_llm("23 días y un coche [1]."), judge(faithful=False, correctness=0.5),
                      retriever_returning({"eva@x": [VACATION]}))
    assert halluc.hallucinated and halluc.unsupported_claims == ["x"] and halluc.correctness == 0.5


def test_errors_do_not_stop_the_run():
    def broken(email):
        raise RuntimeError("BD caída")

    r = run_case(CASE, chat_llm("x"), judge(), broken)
    assert r.error == "RuntimeError: BD caída"


def test_summary_and_report():
    results = [
        run_case(CASE, chat_llm("Son 23 días [1]."), judge(), retriever_returning({"eva@x": [VACATION]})),
        run_case(CASE, chat_llm("Inventado [1]."), judge(faithful=False, correctness=0),
                 retriever_returning({"eva@x": [VACATION]})),
        run_case(EvalCase("c3", "¿Menú?", "eva@x", None), chat_llm("x"), judge(), retriever_returning({})),
    ]
    s = summarize(results)
    assert s["cases"] == 3 and s["errors"] == 0
    assert s["hit_rate"] == 1.0 and s["mrr"] == 1.0 and s["page_hit_rate"] == 1.0
    assert s["faithfulness"] == 0.5 and s["hallucination_rate"] == 0.5
    assert s["correctness"] == 0.5 and s["refusal_accuracy"] == 1.0

    md = render_markdown(s, results)
    assert "| Fidelidad media | 50.0 % |" in md and "| c3 | eva@x |" in md


def test_load_dataset_rejects_duplicates(tmp_path):
    p = tmp_path / "d.jsonl"
    line = json.dumps({"id": "a", "question": "q", "as_user": "u", "expected_answer": None})
    p.write_text(line + "\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repetidos"):
        load_dataset(p)


# ---------- Coherencia del corpus demo ----------

def test_golden_dataset_matches_demo_corpus():
    """Si alguien renombra un documento o cambia páginas, este test avisa antes de evaluar."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = {d["title"]: d for d in manifest["documents"]}
    users = {u["email"] for u in manifest["users"]}
    pages = {
        title: len(extract_pages(MANIFEST.parent / "docs" / d["file"], FileType.TXT))
        for title, d in docs.items()
    }

    cases = load_dataset(DATASET)
    assert len(cases) >= 10
    for case in cases:
        assert case.as_user in users, case.id
        for title in case.expected_documents:
            assert title in docs, f"{case.id}: documento desconocido {title}"
            assert all(1 <= p <= pages[title] for p in case.expected_pages), case.id
    assert any(not c.should_answer for c in cases), "el dataset debe incluir preguntas sin respuesta"
