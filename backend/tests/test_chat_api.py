import pytest

from app.api.deps import embedder_dependency, llm_dependency, retriever_dependency
from app.main import app
from app.services.llm import FakeLLM
from app.services.rag import NO_INFO_ANSWER, REWRITE_PROMPT
from app.services.search import SearchHit
from tests.test_search import TopicEmbedder

VACATION_HIT = SearchHit(10, 1, "Política de vacaciones", 3, "Son 23 días hábiles al año.", 0.03, 0.82)


def answer_or_rewrite(messages):
    if messages[0].content == REWRITE_PROMPT:
        return messages[-1].content.split("Última pregunta: ")[-1]
    return "Tienes 23 días hábiles [1]."


@pytest.fixture
def fake_ai(client):
    """Sustituye LLM y recuperador. `hits` se puede cambiar dentro del test."""
    state = {"hits": [VACATION_HIT], "llm": FakeLLM(answer_or_rewrite)}
    app.dependency_overrides[llm_dependency] = lambda: state["llm"]
    app.dependency_overrides[retriever_dependency] = lambda: (lambda q, k: state["hits"][:k])
    return state


def new_conversation(client, headers, title=None):
    r = client.post("/api/conversations", headers=headers, json={"title": title})
    assert r.status_code == 201
    return r.json()["id"]


def ask(client, headers, conv_id, content):
    return client.post(f"/api/conversations/{conv_id}/messages", headers=headers, json={"content": content})


def test_chat_turn_returns_answer_with_citations(client, user_headers, fake_ai):
    conv_id = new_conversation(client, user_headers)
    r = ask(client, user_headers, conv_id, "¿Cuántos días de vacaciones me corresponden?")
    assert r.status_code == 200
    body = r.json()

    assistant = body["assistant_message"]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Tienes 23 días hábiles [1]."
    assert assistant["sources"][0] | {"content": None} == {
        "n": 1, "chunk_id": 10, "document_id": 1, "document_title": "Política de vacaciones",
        "page_number": 3, "content": None, "score": 0.03, "similarity": 0.82, "cited": True,
    }
    assert assistant["prompt_tokens"] == 100 and assistant["model"] == "fake-llm"
    assert body["user_message"]["content"] == "¿Cuántos días de vacaciones me corresponden?"


def test_history_is_persisted_and_title_set_from_first_question(client, user_headers, fake_ai):
    conv_id = new_conversation(client, user_headers)
    ask(client, user_headers, conv_id, "¿Cuántos días de vacaciones tengo?")
    ask(client, user_headers, conv_id, "¿Y los becarios?")

    conv = client.get(f"/api/conversations/{conv_id}", headers=user_headers).json()
    assert conv["title"] == "¿Cuántos días de vacaciones tengo?"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]

    # El segundo turno recibió el historial (reescritura + respuesta = 3 llamadas en total)
    assert len(fake_ai["llm"].calls) == 3
    assert conv["messages"][3]["search_query"] == "¿Y los becarios?"


def test_no_sources_answer(client, user_headers, fake_ai):
    fake_ai["hits"] = []
    conv_id = new_conversation(client, user_headers)
    body = ask(client, user_headers, conv_id, "¿Menú del comedor?").json()
    assert body["assistant_message"]["content"] == NO_INFO_ANSWER
    assert body["assistant_message"]["sources"] == []


def test_users_cannot_access_others_conversations(client, user_headers, admin_headers, fake_ai):
    conv_id = new_conversation(client, user_headers, "Privada")
    assert client.get(f"/api/conversations/{conv_id}", headers=admin_headers).status_code == 404
    assert ask(client, admin_headers, conv_id, "hola").status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}", headers=admin_headers).status_code == 404
    assert client.get("/api/conversations", headers=admin_headers).json() == []
    assert [c["title"] for c in client.get("/api/conversations", headers=user_headers).json()] == ["Privada"]


def test_delete_conversation_removes_messages(client, user_headers, fake_ai, db):
    from sqlalchemy import func, select

    from app.models.chat import Message

    conv_id = new_conversation(client, user_headers)
    ask(client, user_headers, conv_id, "pregunta")
    assert client.delete(f"/api/conversations/{conv_id}", headers=user_headers).status_code == 204
    assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_llm_failure_returns_502_and_saves_nothing(client, user_headers, fake_ai):
    def boom(_):
        raise TimeoutError("OpenAI no responde")

    fake_ai["llm"] = FakeLLM(boom)
    conv_id = new_conversation(client, user_headers)
    assert ask(client, user_headers, conv_id, "pregunta").status_code == 502
    conv = client.get(f"/api/conversations/{conv_id}", headers=user_headers).json()
    assert conv["messages"] == []


def test_message_validation(client, user_headers, fake_ai):
    conv_id = new_conversation(client, user_headers)
    assert ask(client, user_headers, conv_id, "").status_code == 422
    assert ask(client, user_headers, conv_id, "x" * 4001).status_code == 422


@pytest.mark.postgres
def test_end_to_end_upload_then_chat(client, admin_headers, user_headers):
    """Subida real → chunks + embeddings en pgvector → búsqueda híbrida → respuesta."""
    app.dependency_overrides[embedder_dependency] = lambda: TopicEmbedder()
    llm = FakeLLM(answer_or_rewrite)
    app.dependency_overrides[llm_dependency] = lambda: llm

    for title, content in {
        "Política de vacaciones": "Cada empleado dispone de 23 días hábiles de descanso anual.",
        "Gastos de viaje": "Las dietas de viaje se reembolsan presentando factura.",
    }.items():
        client.post(
            "/api/documents", headers=admin_headers,
            files={"file": ("d.txt", content.encode())}, data={"title": title, "visibility": "public"},
        )

    conv_id = new_conversation(client, user_headers)
    body = ask(client, user_headers, conv_id, "¿Cuántos días de descanso tengo?").json()
    sources = body["assistant_message"]["sources"]
    assert sources[0]["document_title"] == "Política de vacaciones"
    assert sources[0]["cited"] is True
    assert "23 días hábiles" in llm.calls[-1][-1].content
