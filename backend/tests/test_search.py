"""Tests de búsqueda.

- RRF: lógica pura, corre siempre.
- Búsqueda real: necesita PostgreSQL + pgvector (marcados `postgres`).

Para que la búsqueda semántica sea comprobable sin OpenAI usamos `TopicEmbedder`:
un embedder de juguete que asigna una dimensión por tema y trata los sinónimos igual.
Así «días libres» y «descanso» caen en el mismo sitio, como haría un embedding real.
"""
import math

import pytest
from sqlalchemy import text, true

from app.api.deps import embedder_dependency
from app.main import app
from app.services.search import SearchHit, SearchMode, reciprocal_rank_fusion, search

TOPICS = {
    "vacaciones": ["vacaciones", "vacación", "descanso", "libres", "festivos"],
    "seguridad": ["contraseña", "contraseñas", "seguridad", "iso", "acceso"],
    "viajes": ["viaje", "viajes", "dietas", "gastos", "reembolso", "reembolsan", "factura"],
}


class TopicEmbedder:
    dimensions = 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            words = t.lower().replace("¿", " ").replace("?", " ").replace(".", " ").split()
            v = [0.0] * self.dimensions
            for i, synonyms in enumerate(TOPICS.values()):
                v[i] = sum(w.startswith(s) for w in words for s in synonyms)
            v[-1] = 0.1  # evita el vector cero (coseno indefinido)
            norm = math.sqrt(sum(x * x for x in v))
            out.append([x / norm for x in v])
        return out


DOCS = {
    "Política de vacaciones": "Cada empleado dispone de 23 días hábiles de descanso anual retribuido.",
    "Seguridad informática": "Las contraseñas deben cambiarse cada 90 días según la norma ISO-27001.",
    "Gastos de viaje": "Las dietas de viaje se reembolsan presentando la factura original.",
}


def search_all(db, query, **kwargs):
    """Búsqueda sin restricción de permisos (como un admin). Los permisos se prueban en test_permissions.py."""
    return search(db, TopicEmbedder(), query, access=true(), **kwargs)


# ---------- RRF (sin BD) ----------

def hit(chunk_id: int, **kw) -> SearchHit:
    return SearchHit(chunk_id, 1, "doc", 1, f"chunk {chunk_id}", 0.0, **kw)


def test_rrf_rewards_chunks_present_in_both_rankings():
    semantic = [hit(1, similarity=0.9), hit(2, similarity=0.8), hit(3, similarity=0.7)]
    keyword = [hit(3, keyword_rank=0.5), hit(4, keyword_rank=0.4)]
    fused = reciprocal_rank_fusion(semantic, keyword)

    assert fused[0].chunk_id == 3  # 3.º en una, 1.º en otra > 1.º en una sola
    assert fused[0].similarity == 0.7 and fused[0].keyword_rank == 0.5
    assert {h.chunk_id for h in fused} == {1, 2, 3, 4}
    assert fused[0].score == pytest.approx(1 / 63 + 1 / 61)


def test_rrf_does_not_mutate_inputs():
    semantic = [hit(1, similarity=0.9)]
    reciprocal_rank_fusion(semantic, [hit(1, keyword_rank=0.3)])
    assert semantic[0].score == 0.0 and semantic[0].keyword_rank is None


# ---------- Búsqueda real en PostgreSQL ----------

@pytest.fixture
def indexed_docs(client, admin_headers):
    app.dependency_overrides[embedder_dependency] = lambda: TopicEmbedder()
    ids = {}
    for title, content in DOCS.items():
        r = client.post(
            "/api/documents",
            headers=admin_headers,
            files={"file": ("doc.txt", content.encode())},
            data={"title": title, "visibility": "public"},
        )
        assert r.status_code == 202
        ids[title] = r.json()["id"]
    return ids


@pytest.mark.postgres
def test_indexes_exist(db):
    names = set(db.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'")))
    assert {"ix_chunks_embedding_hnsw", "ix_chunks_content_fts"} <= names


@pytest.mark.postgres
def test_semantic_search_finds_synonyms(db, indexed_docs):
    # Ni «días libres» ni «tengo» aparecen literalmente en el documento de vacaciones
    hits = search_all(db, "¿Cuántos días libres tengo?", mode=SearchMode.SEMANTIC)
    assert hits[0].document_title == "Política de vacaciones"
    assert hits[0].page_number == 1
    assert hits[0].similarity > hits[-1].similarity


@pytest.mark.postgres
def test_keyword_search_finds_exact_terms_with_spanish_stemming(db, indexed_docs):
    hits = search_all(db, "ISO-27001", mode=SearchMode.KEYWORD)
    assert [h.document_title for h in hits] == ["Seguridad informática"]

    # Stemming: «reembolso» encuentra «reembolsan»
    hits = search_all(db, "reembolso", mode=SearchMode.KEYWORD)
    assert hits and hits[0].document_title == "Gastos de viaje"


@pytest.mark.postgres
def test_hybrid_combines_both_signals(db, indexed_docs):
    hits = search_all(db, "norma ISO-27001 de contraseñas", mode=SearchMode.HYBRID, top_k=3)
    top = hits[0]
    assert top.document_title == "Seguridad informática"
    assert top.similarity is not None and top.keyword_rank is not None


@pytest.mark.postgres
def test_filters_by_document_ids_and_min_similarity(db, indexed_docs):
    only_travel = [indexed_docs["Gastos de viaje"]]
    hits = search_all(db, "vacaciones", mode=SearchMode.SEMANTIC, document_ids=only_travel)
    assert {h.document_title for h in hits} == {"Gastos de viaje"}

    hits = search_all(db, "vacaciones", mode=SearchMode.SEMANTIC, min_similarity=0.9)
    assert [h.document_title for h in hits] == ["Política de vacaciones"]


@pytest.mark.postgres
def test_documents_not_ready_are_excluded(db, client, admin_headers, indexed_docs):
    doc_id = indexed_docs["Política de vacaciones"]
    db.execute(text("UPDATE documents SET status = 'processing' WHERE id = :id"), {"id": doc_id})
    db.commit()
    hits = search_all(db, "vacaciones descanso", mode=SearchMode.HYBRID)
    assert "Política de vacaciones" not in {h.document_title for h in hits}


@pytest.mark.postgres
def test_search_endpoint(client, user_headers, indexed_docs):
    r = client.post(
        "/api/search",
        headers=user_headers,
        json={"query": "¿Cuántos días de descanso tengo?", "top_k": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "hybrid"
    assert len(body["results"]) <= 2
    assert body["results"][0]["document_title"] == "Política de vacaciones"


def test_search_requires_auth(client):
    assert client.post("/api/search", json={"query": "hola"}).status_code == 401


def test_search_validates_input(client, user_headers):
    r = client.post("/api/search", headers=user_headers, json={"query": "x", "top_k": 50})
    assert r.status_code == 422
