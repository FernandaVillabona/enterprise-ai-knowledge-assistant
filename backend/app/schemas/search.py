from pydantic import BaseModel, ConfigDict, Field

from app.services.search import SearchMode


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: SearchMode = SearchMode.HYBRID
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchHitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    document_id: int
    document_title: str
    page_number: int
    content: str
    score: float
    similarity: float | None
    keyword_rank: float | None


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    results: list[SearchHitRead]
