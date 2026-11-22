"""Fixtures de test.

Dos modos:
- Por defecto, SQLite en memoria: sin Docker y en milisegundos. pgvector guarda el
  vector como texto, suficiente para probar auth e ingesta.
- Con `TEST_DATABASE_URL` apuntando a un PostgreSQL con pgvector (Docker o GitHub
  Actions) se ejecutan además los tests marcados `@pytest.mark.postgres` (búsqueda
  vectorial, full-text, índices). ¡Usa una BD de pruebas: se borran las tablas!

    docker compose up -d db
    docker compose exec db createdb -U kb_user kb_test
    $env:TEST_DATABASE_URL = "postgresql+psycopg://kb_user:kb_password@localhost:5432/kb_test"
    pytest
"""
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.deps import embedder_dependency
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import Base, get_db, get_session_factory
from app.main import app
from app.models.user import User, UserRole
from app.services.embeddings import FakeEmbedder

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
USING_POSTGRES = bool(TEST_DATABASE_URL)

if USING_POSTGRES:
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
else:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # una sola conexión compartida = la BD en memoria persiste
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_conn, _):
        # SQLite ignora las claves foráneas (y ON DELETE CASCADE) si no se activan.
        # PostgreSQL las aplica siempre.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def pytest_collection_modifyitems(config, items):
    if USING_POSTGRES:
        return
    skip = pytest.mark.skip(reason="requiere PostgreSQL + pgvector (define TEST_DATABASE_URL)")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def db() -> Iterator[Session]:
    """Sesión para preparar datos y comprobar resultados desde el test."""
    Base.metadata.drop_all(engine)  # por si una ejecución anterior se interrumpió
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    """Cada test guarda los archivos subidos en una carpeta temporal propia."""
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path / "documents")
    return tmp_path / "documents"


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    def _get_db() -> Iterator[Session]:
        # Sesión nueva por petición, como en producción (evita datos cacheados viejos)
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_session_factory] = lambda: TestingSession
    app.dependency_overrides[embedder_dependency] = lambda: FakeEmbedder()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_user(db: Session, email: str, role: UserRole) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=hash_password("password-123"),
        role=role,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def admin_user(db: Session) -> User:
    return _make_user(db, "admin@empresa.com", UserRole.ADMIN)


@pytest.fixture
def admin_headers(admin_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(admin_user.id)}"}


@pytest.fixture
def user_headers(db: Session) -> dict[str, str]:
    user = _make_user(db, "empleado@empresa.com", UserRole.USER)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}
