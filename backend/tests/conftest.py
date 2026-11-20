"""Fixtures de test.

Para la fase 1 usamos SQLite en memoria: los tests corren sin Docker y en milisegundos.
Cuando lleguemos a pgvector (fase 3) los tests de búsqueda necesitarán PostgreSQL real
(lo haremos con un servicio de Postgres en GitHub Actions).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.security import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.user import User, UserRole

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # una sola conexión compartida = la BD en memoria persiste
)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db() -> Session:
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db: Session) -> User:
    user = User(
        email="admin@empresa.com",
        full_name="Admin",
        hashed_password=hash_password("admin-pass-123"),
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    return user
