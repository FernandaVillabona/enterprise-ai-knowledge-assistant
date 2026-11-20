"""División de páginas en fragmentos (chunks) medidos en tokens.

¿Por qué trocear?
- Los embeddings representan mejor un texto corto y temático que uno largo y mezclado.
- Al preguntar, solo enviamos al LLM los trozos relevantes (menos coste, menos ruido).

Decisiones:
- Medimos en *tokens* (tiktoken, cl100k_base = el tokenizador de text-embedding-3),
  no en caracteres, porque los límites y el coste de OpenAI van por tokens.
- Un chunk nunca cruza páginas: así cada chunk tiene una página exacta para citar.
- Cortamos por fronteras naturales (párrafo → frase → tokens) para no partir ideas.
- Solapamiento (overlap): el inicio de cada chunk repite el final del anterior, para
  que una idea que cae justo en el corte siga siendo recuperable.
"""
import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from app.services.extraction import Page


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


@dataclass(frozen=True)
class ChunkData:
    chunk_index: int
    page_number: int
    content: str
    token_count: int


_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


@dataclass(frozen=True)
class _Unit:
    text: str
    tokens: int
    starts_paragraph: bool  # para reconstruir el texto con sus saltos de párrafo reales


def _split_units(text: str, max_tokens: int) -> list[_Unit]:
    """Divide en unidades que quepan en max_tokens: párrafos, luego frases, luego tokens."""
    units: list[_Unit] = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        n = count_tokens(paragraph)
        if n <= max_tokens:
            units.append(_Unit(paragraph, n, True))
            continue
        first = True
        for sentence in (s.strip() for s in _SENTENCE_END.split(paragraph)):
            if not sentence:
                continue
            n = count_tokens(sentence)
            if n <= max_tokens:
                units.append(_Unit(sentence, n, first))
            else:
                # Frase gigante (tablas, listas sin puntuación…): corte duro por tokens
                tokens = _encoding().encode(sentence)
                for i in range(0, len(tokens), max_tokens):
                    piece = _encoding().decode(tokens[i : i + max_tokens])
                    units.append(_Unit(piece, count_tokens(piece), first and i == 0))
            first = False
    return units


def _join(units: list[_Unit]) -> str:
    parts = [units[0].text]
    for u in units[1:]:
        parts.append(("\n\n" if u.starts_paragraph else " ") + u.text)
    return "".join(parts)


def _chunk_page(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    chunks: list[str] = []
    current: list[_Unit] = []
    current_tokens = 0

    for unit in _split_units(text, max_tokens):
        if current and current_tokens + unit.tokens > max_tokens:
            chunks.append(_join(current))
            # Arrancamos el siguiente chunk con las últimas unidades (overlap)
            overlap: list[_Unit] = []
            overlap_size = 0
            for u in reversed(current):
                if overlap_size + u.tokens > overlap_tokens:
                    break
                overlap.insert(0, u)
                overlap_size += u.tokens
            if overlap_size + unit.tokens > max_tokens:
                overlap, overlap_size = [], 0
            current, current_tokens = overlap, overlap_size
        current.append(unit)
        current_tokens += unit.tokens

    if current:
        chunks.append(_join(current))
    return chunks


def chunk_pages(pages: list[Page], max_tokens: int, overlap_tokens: int) -> list[ChunkData]:
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens debe ser menor que max_tokens")

    result: list[ChunkData] = []
    for page in pages:
        for content in _chunk_page(page.text, max_tokens, overlap_tokens):
            result.append(
                ChunkData(
                    chunk_index=len(result),
                    page_number=page.number,
                    content=content,
                    token_count=count_tokens(content),
                )
            )
    return result
