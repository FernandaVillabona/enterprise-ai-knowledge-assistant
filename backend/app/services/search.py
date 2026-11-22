"""Recuperación de fragmentos: búsqueda semántica, por palabras clave e híbrida.

- Semántica (vectorial): compara el embedding de la pregunta con el de cada chunk
  usando distancia coseno (`<=>` en pgvector). Entiende sinónimos y paráfrasis
  («días libres» ≈ «vacaciones»), pero puede fallar con términos exactos:
  códigos («ISO-27001»), nombres propios, números de artículo…
- Palabras clave (full-text de PostgreSQL): coincidencia de términos con stemming
  en español. Precisa con términos exactos, ciega a sinónimos.
- Híbrida: ejecuta ambas y las fusiona con Reciprocal Rank Fusion (RRF). Es lo que
  usan la mayoría de sistemas RAG en producción porque combina lo mejor de las dos.
"""
import enum
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.document import FTS_CONFIG, Chunk, Document, DocumentStatus, chunk_tsvector
from app.services.embeddings import Embedder

RRF_K = 60  # constante estándar de RRF (Cormack et al., 2009)


class SearchMode(str, enum.Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass
class SearchHit:
    chunk_id: int
    document_id: int
    document_title: str
    page_number: int
    content: str
    score: float  # puntuación final usada para ordenar (depende del modo)
    similarity: float | None = None  # similitud coseno 0..1 (si hubo búsqueda semántica)
    keyword_rank: float | None = None  # ts_rank_cd (si hubo coincidencia por palabras)


def _base_query(document_ids: list[int] | None):
    """Columnas comunes y filtros: solo documentos procesados (y, en la fase 5, autorizados)."""
    q = (
        select(
            Chunk.id,
            Chunk.document_id,
            Document.title,
            Chunk.page_number,
            Chunk.content,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.status == DocumentStatus.READY)
    )
    if document_ids is not None:
        q = q.where(Chunk.document_id.in_(document_ids))
    return q


def _configure_hnsw(db: Session) -> None:
    """Ajustes de pgvector para esta transacción (SET LOCAL = solo dura la transacción).

    - ef_search: cuántos candidatos explora el índice. Más alto = mejor recall, más lento.
    - iterative_scan (pgvector >= 0.8): con filtros (WHERE status/permisos) el índice
      podría devolver menos de `top_k` filas porque filtra DESPUÉS de elegir candidatos.
      El escaneo iterativo sigue buscando hasta llenar el LIMIT. Clave en la fase 5,
      cuando filtremos por permisos.
    """
    db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))


def semantic_search(
    db: Session,
    query_vector: list[float],
    top_k: int,
    document_ids: list[int] | None = None,
    min_similarity: float = 0.0,
) -> list[SearchHit]:
    _configure_hnsw(db)
    distance = Chunk.embedding.cosine_distance(query_vector)
    rows = db.execute(
        _base_query(document_ids).add_columns(distance.label("distance")).order_by(distance).limit(top_k)
    ).all()
    hits = []
    for r in rows:
        similarity = 1 - float(r.distance)  # distancia coseno 0..2 → similitud
        if similarity < min_similarity:
            continue
        hits.append(
            SearchHit(r.id, r.document_id, r.title, r.page_number, r.content, similarity, similarity)
        )
    return hits


def keyword_search(
    db: Session, query: str, top_k: int, document_ids: list[int] | None = None
) -> list[SearchHit]:
    # websearch_to_tsquery acepta sintaxis tipo Google: "frase exacta", -excluir, OR
    tsquery = func.websearch_to_tsquery(FTS_CONFIG, query)
    tsvector = chunk_tsvector()  # misma expresión que el índice GIN
    rank = func.ts_rank_cd(tsvector, tsquery)
    rows = db.execute(
        _base_query(document_ids)
        .add_columns(rank.label("rank"))
        .where(tsvector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(top_k)
    ).all()
    return [
        SearchHit(r.id, r.document_id, r.title, r.page_number, r.content, float(r.rank), keyword_rank=float(r.rank))
        for r in rows
    ]


def reciprocal_rank_fusion(*rankings: list[SearchHit], k: int = RRF_K) -> list[SearchHit]:
    """Fusiona listas ordenadas: score(d) = Σ 1 / (k + posición_de_d_en_cada_lista).

    Ventaja: no hay que normalizar puntuaciones de escalas distintas (coseno 0..1 vs
    ts_rank sin límite); solo importa la *posición*. Un chunk que aparece arriba en
    ambas listas gana a uno que solo está en una.
    """
    fused: dict[int, SearchHit] = {}
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1 / (k + position)
            if hit.chunk_id in fused:
                existing = fused[hit.chunk_id]
                existing.similarity = existing.similarity if existing.similarity is not None else hit.similarity
                existing.keyword_rank = existing.keyword_rank if existing.keyword_rank is not None else hit.keyword_rank
            else:
                fused[hit.chunk_id] = SearchHit(**vars(hit))
    for chunk_id, hit in fused.items():
        hit.score = scores[chunk_id]
    return sorted(fused.values(), key=lambda h: h.score, reverse=True)


def search(
    db: Session,
    embedder: Embedder,
    query: str,
    top_k: int = 5,
    mode: SearchMode = SearchMode.HYBRID,
    document_ids: list[int] | None = None,
    min_similarity: float = 0.0,
) -> list[SearchHit]:
    if mode is SearchMode.KEYWORD:
        return keyword_search(db, query, top_k, document_ids)

    query_vector = embedder.embed([query])[0]
    if mode is SearchMode.SEMANTIC:
        return semantic_search(db, query_vector, top_k, document_ids, min_similarity)

    # Híbrida: pedimos más candidatos de cada lado para que la fusión tenga material
    candidates = top_k * 4
    semantic = semantic_search(db, query_vector, candidates, document_ids, min_similarity)
    keyword = keyword_search(db, query, candidates, document_ids)
    return reciprocal_rank_fusion(semantic, keyword)[:top_k]
