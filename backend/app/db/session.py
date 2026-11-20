"""Conexión a PostgreSQL con SQLAlchemy 2.0."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Clase base de todos los modelos ORM (se usará desde la fase 1)."""


def get_session_factory() -> sessionmaker:
    """Dependencia para tareas en segundo plano, que necesitan abrir su propia sesión
    (la de la petición ya se ha cerrado cuando se ejecutan). Los tests la sustituyen."""
    return SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: abre una sesión por petición y la cierra al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
