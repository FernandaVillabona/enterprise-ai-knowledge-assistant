"""Extracción de texto por página para PDF, DOCX y TXT.

Devolvemos una lista de `Page(number, text)` en vez de un único texto, porque el número
de página es lo que luego nos permite citar «Política de vacaciones, pág. 3».

- PDF: páginas reales (pypdf).
- DOCX: Word no guarda páginas (se calculan al renderizar). Usamos los saltos de página
  explícitos y los `lastRenderedPageBreak` que Word escribe al guardar; es una buena
  aproximación de la página que ve el usuario.
- TXT: un salto de página (form feed, \\f) separa páginas; si no hay, todo es la página 1.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from pypdf import PdfReader

from app.models.document import FileType


class ExtractionError(Exception):
    pass


@dataclass(frozen=True)
class Page:
    number: int  # empieza en 1
    text: str


def clean_text(text: str) -> str:
    """Normaliza el texto extraído.

    - Quita caracteres NUL: PostgreSQL rechaza '\\x00' en columnas TEXT.
    - Une palabras partidas con guion al final de línea ("vaca-\\nciones").
    - Colapsa espacios repetidos pero conserva los saltos de párrafo (\\n\\n),
      que el chunker usa como frontera natural.
    """
    text = text.replace("\x00", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(path: Path) -> list[Page]:
    try:
        reader = PdfReader(path)
    except Exception as exc:  # pypdf lanza varios tipos según el fallo
        raise ExtractionError(f"PDF ilegible: {exc}") from exc
    if reader.is_encrypted:
        raise ExtractionError("El PDF está protegido con contraseña")
    return [Page(i, clean_text(p.extract_text() or "")) for i, p in enumerate(reader.pages, 1)]


def _paragraph_breaks_page(paragraph) -> bool:
    """¿El párrafo contiene un salto de página (explícito o renderizado por Word)?"""
    el = paragraph._p
    for br in el.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return next(el.iter(qn("w:lastRenderedPageBreak")), None) is not None


def _extract_docx(path: Path) -> list[Page]:
    try:
        doc = DocxDocument(str(path))
    except Exception as exc:
        raise ExtractionError(f"DOCX ilegible: {exc}") from exc

    pages: list[list[str]] = [[]]
    for paragraph in doc.paragraphs:
        # El salto pertenece al párrafo donde empieza la página nueva
        if _paragraph_breaks_page(paragraph) and pages[-1]:
            pages.append([])
        if paragraph.text.strip():
            pages[-1].append(paragraph.text)

    # Las tablas no están en doc.paragraphs: las añadimos al final como texto plano
    # (simplificación: perdemos su posición exacta de página).
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                pages[-1].append(" | ".join(cells))

    return [Page(i, clean_text("\n\n".join(p))) for i, p in enumerate(pages, 1)]


def _extract_txt(path: Path) -> list[Page]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")  # nunca falla: cualquier byte es válido en latin-1
    return [Page(i, clean_text(t)) for i, t in enumerate(text.split("\f"), 1)]


_EXTRACTORS = {
    FileType.PDF: _extract_pdf,
    FileType.DOCX: _extract_docx,
    FileType.TXT: _extract_txt,
}


def extract_pages(path: Path, file_type: FileType) -> list[Page]:
    """Extrae el texto de cada página. Lanza ExtractionError si no hay texto útil."""
    pages = _EXTRACTORS[file_type](path)
    if not any(p.text for p in pages):
        raise ExtractionError(
            "No se encontró texto. Si es un PDF escaneado necesitaría OCR (no soportado aún)."
        )
    return pages
