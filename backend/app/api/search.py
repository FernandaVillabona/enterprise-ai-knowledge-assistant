from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, EmbedderDep
from app.schemas.search import SearchHitRead, SearchRequest, SearchResponse
from app.services import search as search_service
from app.services.permissions import document_access_condition

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search(data: SearchRequest, user: CurrentUser, db: DbSession, embedder: EmbedderDep) -> SearchResponse:
    """Busca los fragmentos más relevantes entre los documentos que el usuario puede ver."""
    hits = search_service.search(
        db,
        embedder,
        data.query,
        access=document_access_condition(user),
        top_k=data.top_k,
        mode=data.mode,
        min_similarity=data.min_similarity,
    )
    return SearchResponse(
        query=data.query,
        mode=data.mode,
        results=[SearchHitRead.model_validate(h) for h in hits],
    )
