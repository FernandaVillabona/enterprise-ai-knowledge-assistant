"""Dependencias reutilizables: usuario autenticado, roles y servicios de IA.

Los servicios de IA (embeddings, LLM, recuperador) se inyectan como dependencias
para que los tests puedan sustituirlos con `app.dependency_overrides`.
"""
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services import search as search_service
from app.services.embeddings import Embedder, get_embedder
from app.services.llm import ChatLLM, get_judge_llm, get_llm
from app.services.permissions import document_access_condition
from app.services.rag import Retriever

# tokenUrl le dice a Swagger (/docs) dónde hacer login con el botón "Authorize"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token caducado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_error

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol de administrador")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def embedder_dependency() -> Embedder:
    try:
        return get_embedder()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


EmbedderDep = Annotated[Embedder, Depends(embedder_dependency)]


def llm_dependency() -> ChatLLM:
    try:
        return get_llm()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


LLMDep = Annotated[ChatLLM, Depends(llm_dependency)]


def judge_llm_dependency() -> ChatLLM:
    try:
        return get_judge_llm()
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


JudgeLLMDep = Annotated[ChatLLM, Depends(judge_llm_dependency)]


def retriever_dependency(db: DbSession, embedder: EmbedderDep, user: CurrentUser) -> Retriever:
    """Búsqueda híbrida que usa el chat, limitada a los documentos que `user` puede ver."""
    min_similarity = get_settings().rag_min_similarity
    access = document_access_condition(user)

    def retrieve(query: str, top_k: int) -> list[search_service.SearchHit]:
        return search_service.search(
            db, embedder, query, access=access, top_k=top_k,
            mode=search_service.SearchMode.HYBRID, min_similarity=min_similarity,
        )

    return retrieve


RetrieverDep = Annotated[Retriever, Depends(retriever_dependency)]
