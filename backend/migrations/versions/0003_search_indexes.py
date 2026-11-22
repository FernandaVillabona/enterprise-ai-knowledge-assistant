"""search indexes: HNSW (vector) + GIN (full-text)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22

HNSW (Hierarchical Navigable Small World) es un índice de vecinos aproximados:
en vez de comparar la pregunta con TODOS los vectores (O(n)), navega un grafo
por capas y encuentra los más cercanos en tiempo casi logarítmico, a cambio de
una pequeña pérdida de exactitud (recall).

- vector_cosine_ops: el índice sirve para el operador de distancia coseno (<=>),
  que es el que usamos al buscar. Un índice creado para L2 (<->) NO se usaría.
- m / ef_construction: conexiones por nodo y esfuerzo al construir. Más alto =
  mejor recall, índice más grande y más lento de construir. 16/64 son los valores
  por defecto de pgvector.

El índice GIN sobre to_tsvector permite la búsqueda por palabras clave
(full-text search) que combinamos con la vectorial en la búsqueda híbrida.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX ix_chunks_content_fts ON chunks "
        "USING gin (to_tsvector('spanish'::regconfig, content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
