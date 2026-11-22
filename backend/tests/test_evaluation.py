import json

import pytest

from app.services.evaluation import (
    Evaluation,
    Verdict,
    evaluate_correctness,
    evaluate_faithfulness,
    initial_evaluation,
    parse_json_object,
)
from app.services.llm import FakeLLM
from app.services.rag import NO_INFO_ANSWER

SOURCES = [
    {"n": 1, "document_title": "Vacaciones", "page_number": 1, "content": "Son 23 días hábiles al año."},
    {"n": 2, "document_title": "Teletrabajo", "page_number": 2, "content": "Compensación de 30 euros al mes."},
]


def judge_returning(claims: list[tuple[str, bool]]) -> FakeLLM:
    payload = {"claims": [{"claim": c, "supported": s, "sources": [1] if s else []} for c, s in claims]}
    return FakeLLM(lambda m: json.dumps(payload))


# ---------- Parseo de la salida del juez ----------

def test_parse_json_object_tolerates_fences_and_prose():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Aquí tienes: {"a": [1, 2]} ¡listo!') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        parse_json_object("sin json")


# ---------- Fidelidad ----------

def test_fully_supported_answer():
    judge = judge_returning([("23 días hábiles", True)])
    ev = evaluate_faithfulness(judge, "Tienes 23 días hábiles [1].", SOURCES)
    assert ev.verdict == Verdict.SUPPORTED and ev.faithfulness == 1.0
    assert not ev.is_flagged(threshold=1.0)
    # El juez recibe las fuentes y la respuesta, y se le pide JSON
    prompt = judge.calls[0][1].content
    assert "[1] Vacaciones (pág. 1):\nSon 23 días" in prompt and "Tienes 23 días" in prompt


def test_partially_supported_answer_is_flagged():
    judge = judge_returning([("23 días hábiles", True), ("5 días extra por antigüedad", False)])
    ev = evaluate_faithfulness(judge, "23 días [1] y 5 extra por antigüedad [1].", SOURCES)
    assert ev.verdict == Verdict.PARTIAL and ev.faithfulness == 0.5
    assert ev.is_flagged(threshold=1.0)
    assert not ev.is_flagged(threshold=0.5)  # umbral configurable


def test_unsupported_answer():
    judge = judge_returning([("a", False), ("b", False), ("c", True)])
    ev = evaluate_faithfulness(judge, "Respuesta inventada [1].", SOURCES)
    assert ev.verdict == Verdict.UNSUPPORTED and ev.faithfulness == pytest.approx(0.333)


def test_no_info_answer_is_not_judged():
    judge = judge_returning([])
    ev = evaluate_faithfulness(judge, NO_INFO_ANSWER, SOURCES)
    assert ev.verdict == Verdict.NO_ANSWER and ev.faithfulness is None and judge.calls == []
    assert evaluate_faithfulness(judge, "algo", []).verdict == Verdict.NO_ANSWER


def test_judge_failure_is_recorded_not_flagged():
    ev = evaluate_faithfulness(FakeLLM(lambda m: "no es json"), "Son 23 días [1].", SOURCES)
    assert ev.verdict == Verdict.ERROR and ev.error
    assert not ev.is_flagged(threshold=1.0)


def test_deterministic_flags_win_even_if_judge_approves():
    judge = judge_returning([("23 días", True)])
    uncited = evaluate_faithfulness(judge, "Tienes 23 días.", SOURCES)
    assert uncited.uncited and uncited.is_flagged(threshold=1.0)
    invalid = evaluate_faithfulness(judge, "Tienes 23 días [1].", SOURCES, invalid_citations=[7])
    assert invalid.is_flagged(threshold=1.0)


def test_initial_evaluation():
    assert initial_evaluation("23 días [1].", SOURCES, [], judged=True).verdict == Verdict.PENDING
    assert initial_evaluation("23 días [1].", SOURCES, [], judged=False).verdict == Verdict.NOT_EVALUATED
    assert initial_evaluation(NO_INFO_ANSWER, [], [], judged=True).verdict == Verdict.NO_ANSWER
    pending_uncited = initial_evaluation("23 días.", SOURCES, [], judged=True)
    assert pending_uncited.is_flagged(threshold=1.0)
    assert Evaluation(Verdict.PENDING, None).is_flagged(1.0) is False


# ---------- Corrección frente a la referencia ----------

def test_correctness_score_is_clamped():
    score, reason = evaluate_correctness(
        FakeLLM(lambda m: '{"score": 7, "reason": "ok"}'), "¿Días?", "23", "23 días"
    )
    assert score == 1.0 and reason == "ok"
