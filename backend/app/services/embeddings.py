"""Generación de embeddings.

Un *embedding* es un vector de números (1536 para text-embedding-3-small) que
representa el significado de un texto: textos con significado parecido quedan
cerca en ese espacio. Así buscamos por significado y no por palabras exactas
(«días libres» encuentra «vacaciones»).

Definimos una interfaz (`Embedder`) para que el resto del código no dependa de
OpenAI directamente: en los tests usamos `FakeEmbedder`, sin red ni coste.
"""
import hashlib
import math
from functools import lru_cache
from typing import Protocol

from openai import OpenAI

from app.core.config import get_settings


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, dimensions: int, batch_size: int = 100):
        if not api_key:
            raise RuntimeError("Falta OPENAI_API_KEY en el .env")
        # max_retries: el SDK reintenta con backoff ante 429 (rate limit) y errores 5xx
        self.client = OpenAI(api_key=api_key, max_retries=5)
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        # Enviamos por lotes: una petición por texto sería lentísima
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            response = self.client.embeddings.create(
                model=self.model, input=batch, dimensions=self.dimensions
            )
            # La API puede devolver los resultados en otro orden: ordenamos por índice
            vectors.extend(d.embedding for d in sorted(response.data, key=lambda d: d.index))
        return vectors


class FakeEmbedder:
    """Embedder determinista para tests: mismo texto → mismo vector, sin llamar a la API."""

    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [seed[i % len(seed)] / 255 - 0.5 + i * 1e-6 for i in range(self.dimensions)]
        norm = math.sqrt(sum(x * x for x in raw))
        return [x / norm for x in raw]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    return OpenAIEmbedder(
        api_key=s.openai_api_key,
        model=s.openai_embedding_model,
        dimensions=s.embedding_dimensions,
        batch_size=s.embedding_batch_size,
    )
