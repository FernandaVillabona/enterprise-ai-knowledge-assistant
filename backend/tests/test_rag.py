"""Tests del pipeline RAG con un LLM y un recuperador falsos (sin red, deterministas)."""
from app.services.llm import ChatMessage, FakeLLM
from app.services.rag import (
    NO_INFO_ANSWER,
    REWRITE_PROMPT,
    SYSTEM_PROMPT,
    answer_question,
    extract_citations,
    remove_citations,
)
from app.services.search import SearchHit

VACATION_HIT = SearchHit(10, 1, "Política de vacaciones", 3, "Son 23 días hábiles al año.", 0.03, 0.82)
TRAVEL_HIT = SearchHit(20, 2, "Gastos de viaje", 1, "Las dietas se reembolsan con factura.", 0.02, 0.31)


def fake_retriever(hits):
    calls = []

    def retrieve(query: str, top_k: int):
        calls.append(query)
        return hits[:top_k]

    retrieve.calls = calls
    return retrieve


def is_rewrite(messages: list[ChatMessage]) -> bool:
    return messages[0].content == REWRITE_PROMPT


# ---------- Citas ----------

def test_extract_citations_formats_and_order():
    assert extract_citations("A [2]. B [1][3]. C [2, 4]. D [1].") == [2, 1, 3, 4]
    assert extract_citations("Sin citas") == []


def test_remove_citations_keeps_valid_ones():
    text = "Son 23 días [1][7]. Se reembolsan [2, 9]. Otro dato [9]."
    assert remove_citations(text, {7, 9}) == "Son 23 días [1]. Se reembolsan [2]. Otro dato."


# ---------- Pipeline ----------

def test_answer_cites_sources_and_builds_grounded_prompt():
    llm = FakeLLM(lambda m: "Tienes 23 días hábiles de vacaciones [1].")
    result = answer_question(llm, fake_retriever([VACATION_HIT, TRAVEL_HIT]), "¿Cuántas vacaciones tengo?")

    assert result.answer == "Tienes 23 días hábiles de vacaciones [1]."
    assert [s.document_title for s in result.cited_sources] == ["Política de vacaciones"]
    assert result.sources[1].cited is False
    assert result.cited_sources[0].page_number == 3
    assert result.prompt_tokens == 100 and result.model == "fake-llm"

    # Sin historial no se reescribe: una única llamada al LLM
    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert system.content == SYSTEM_PROMPT
    assert '<fuente id="1" documento="Política de vacaciones" pagina="3">' in user.content
    assert "Son 23 días hábiles" in user.content
    assert user.content.endswith("Pregunta: ¿Cuántas vacaciones tengo?")


def test_no_relevant_sources_skips_llm():
    llm = FakeLLM(lambda m: "no debería llamarse")
    result = answer_question(llm, fake_retriever([]), "¿Cuál es el menú de hoy?")
    assert result.answer == NO_INFO_ANSWER
    assert result.sources == [] and llm.calls == []


def test_hallucinated_citations_are_removed_and_reported():
    llm = FakeLLM(lambda m: "Son 23 días [1] y 5 de libre disposición [4].")
    result = answer_question(llm, fake_retriever([VACATION_HIT]), "¿Vacaciones?")
    assert result.answer == "Son 23 días [1] y 5 de libre disposición."
    assert result.invalid_citations == [4]


def test_follow_up_question_is_rewritten_with_history():
    def responder(messages):
        if is_rewrite(messages):
            return "Días de vacaciones de los becarios"
        return "Los becarios tienen 23 días [1]."

    llm = FakeLLM(responder)
    retrieve = fake_retriever([VACATION_HIT])
    history = [
        ChatMessage("user", "¿Cuántos días de vacaciones tengo?"),
        ChatMessage("assistant", "Tienes 23 días hábiles [1]."),
    ]
    result = answer_question(llm, retrieve, "¿Y los becarios?", history)

    assert retrieve.calls == ["Días de vacaciones de los becarios"]
    assert result.search_query == "Días de vacaciones de los becarios"
    assert "¿Cuántos días de vacaciones tengo?" in llm.calls[0][1].content  # historial en la reescritura
    # La respuesta final incluye el historial como mensajes previos
    answer_messages = llm.calls[1]
    assert [m.role for m in answer_messages] == ["system", "user", "assistant", "user"]
    assert result.prompt_tokens == 200  # reescritura + respuesta


def test_history_is_truncated(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rag_history_messages", 2)
    llm = FakeLLM(lambda m: "consulta" if is_rewrite(m) else "ok [1]")
    history = [ChatMessage("user" if i % 2 == 0 else "assistant", f"m{i}") for i in range(10)]
    answer_question(llm, fake_retriever([VACATION_HIT]), "pregunta", history)
    assert [m.content for m in llm.calls[1][1:-1]] == ["m8", "m9"]
