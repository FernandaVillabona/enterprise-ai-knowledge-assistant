"""Evaluación online en el chat, feedback y endpoints de calidad para admins."""
import json

import pytest

from app.api.deps import judge_llm_dependency, llm_dependency, retriever_dependency
from app.main import app
from app.services.llm import FakeLLM
from app.services.rag import REWRITE_PROMPT
from app.services.search import SearchHit

HIT = SearchHit(10, 1, "Política de vacaciones", 3, "Son 23 días hábiles al año.", 0.03, 0.82)


@pytest.fixture
def chat(client):
    """Chat con LLM, recuperador y juez falsos configurables desde el test."""
    state = {
        "answer": "Tienes 23 días hábiles [1].",
        "judge": FakeLLM(lambda m: '{"claims": [{"claim": "23 días", "supported": true, "sources": [1]}]}'),
    }
    app.dependency_overrides[llm_dependency] = lambda: FakeLLM(
        lambda m: "consulta" if m[0].content == REWRITE_PROMPT else state["answer"]
    )
    app.dependency_overrides[retriever_dependency] = lambda: (lambda q, k: [HIT])
    app.dependency_overrides[judge_llm_dependency] = lambda: state["judge"]
    return state


def ask(client, headers, question="¿Vacaciones?"):
    conv = client.post("/api/conversations", headers=headers, json={}).json()["id"]
    turn = client.post(f"/api/conversations/{conv}/messages", headers=headers, json={"content": question}).json()
    return conv, turn["assistant_message"]


def stored_answer(client, headers, conv):
    return client.get(f"/api/conversations/{conv}", headers=headers).json()["messages"][-1]


def test_answer_is_judged_in_background(client, user_headers, chat):
    conv, immediate = ask(client, user_headers)
    assert immediate["evaluation"]["verdict"] == "pending"  # respuesta inmediata, sin esperar al juez

    stored = stored_answer(client, user_headers, conv)
    assert stored["evaluation"]["verdict"] == "supported"
    assert stored["faithfulness_score"] == 1.0 and stored["flagged"] is False
    assert len(chat["judge"].calls) == 1


def test_hallucinated_answer_is_flagged(client, user_headers, chat):
    chat["judge"] = FakeLLM(lambda m: json.dumps({"claims": [
        {"claim": "23 días", "supported": True, "sources": [1]},
        {"claim": "y un coche de empresa", "supported": False, "sources": []},
    ]}))
    conv, _ = ask(client, user_headers)
    stored = stored_answer(client, user_headers, conv)
    assert stored["evaluation"]["verdict"] == "partially_supported"
    assert stored["faithfulness_score"] == 0.5 and stored["flagged"] is True


def test_uncited_answer_is_flagged_immediately(client, user_headers, chat):
    chat["answer"] = "Tienes 23 días hábiles."
    _, immediate = ask(client, user_headers)
    assert immediate["evaluation"]["uncited"] is True and immediate["flagged"] is True


def test_auto_evaluation_can_be_disabled(client, user_headers, chat, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "eval_auto_enabled", False)
    conv, _ = ask(client, user_headers)
    assert stored_answer(client, user_headers, conv)["evaluation"]["verdict"] == "not_evaluated"
    assert chat["judge"].calls == []


# ---------- Feedback ----------

def test_feedback(client, user_headers, admin_headers, chat):
    conv, answer = ask(client, user_headers)
    url = f"/api/conversations/{conv}/messages/{answer['id']}/feedback"

    r = client.post(url, headers=user_headers, json={"rating": -1, "comment": "Falta el caso de becarios"})
    assert r.status_code == 200
    assert r.json()["feedback_rating"] == -1 and r.json()["flagged"] is True  # 👎 → revisión

    assert client.post(url, headers=user_headers, json={"rating": 5}).status_code == 422
    assert client.post(url, headers=admin_headers, json={"rating": 1}).status_code == 404  # ajena
    question_id = answer["id"] - 1
    r = client.post(f"/api/conversations/{conv}/messages/{question_id}/feedback", headers=user_headers,
                    json={"rating": 1})
    assert r.status_code == 404  # solo se valoran respuestas del asistente


# ---------- Métricas y cola de revisión ----------

def test_quality_metrics_and_review_queue(client, user_headers, admin_headers, chat):
    ask(client, user_headers, "¿Cuántos días?")  # respaldada
    chat["judge"] = FakeLLM(lambda m: '{"claims": [{"claim": "x", "supported": false, "sources": []}]}')
    ask(client, user_headers, "¿Y el coche?")  # alucinada → marcada
    app.dependency_overrides[retriever_dependency] = lambda: (lambda q, k: [])
    ask(client, user_headers, "¿Menú?")  # sin información

    m = client.get("/api/admin/metrics", headers=admin_headers).json()
    assert m["answers"] == 3 and m["no_info_answers"] == 1 and m["no_info_rate"] == pytest.approx(0.333)
    assert m["evaluated"] == 2 and m["avg_faithfulness"] == 0.5 and m["hallucination_rate"] == 0.5
    assert m["flagged"] == 1 and m["prompt_tokens"] > 0

    flagged = client.get("/api/admin/flagged", headers=admin_headers).json()
    assert len(flagged) == 1
    assert flagged[0]["question"] == "¿Y el coche?" and flagged[0]["user_email"] == "empleado@empresa.com"

    msg_id = flagged[0]["message_id"]
    assert client.post(f"/api/admin/flagged/{msg_id}/resolve", headers=admin_headers).status_code == 204
    assert client.get("/api/admin/flagged", headers=admin_headers).json() == []
    assert client.post(f"/api/admin/flagged/{msg_id}/resolve", headers=admin_headers).status_code == 404


def test_quality_endpoints_require_admin(client, user_headers):
    assert client.get("/api/admin/metrics", headers=user_headers).status_code == 403
    assert client.get("/api/admin/flagged", headers=user_headers).status_code == 403
