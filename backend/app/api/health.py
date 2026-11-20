from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Comprueba que la API responde, que hay conexión a la BD y que pgvector está activo."""
    db.execute(text("SELECT 1"))
    pgvector = db.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    return {"status": "ok", "database": "ok", "pgvector": pgvector or "missing"}
