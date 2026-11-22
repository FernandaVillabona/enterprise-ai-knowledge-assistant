from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.documents import EmbedderDep
from app.schemas.search import SearchHitRead, SearchRequest, SearchResponse
from app.services import search as search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search(data: SearchRequest, _: CurrentUser, db: DbSession, embedder: EmbedderDep) -> SearchResponse:
    """Busca los fragmentos más relevantes para una pregunta.

    ⚠️ Fase 3: cualquier usuario autenticado busca en TODOS los documentos.
    En la fase 5 se filtrará por los documentos que el usuario tiene autorizados.
    """
    hits = search_service.search(
        db,
        embedder,
        data.query,
        top_k=data.top_k,
        mode=data.mode,
        min_similarity=data.min_similarity,
    )
    return SearchResponse(
        query=data.query,
        mode=data.mode,
        results=[SearchHitRead.model_validate(h) for h in hits],
    )
