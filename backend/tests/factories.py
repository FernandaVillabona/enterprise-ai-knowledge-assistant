"""Generadores de archivos de prueba (PDF, DOCX) sin depender de archivos binarios en el repo."""
import io

from docx import Document as DocxDocument
from docx.enum.text import WD_BREAK


def make_pdf(pages: list[str]) -> bytes:
    """PDF mínimo válido con una línea de texto por página (fuente Helvetica)."""
    objects: list[bytes] = []
    n = len(pages)
    page_ids = [4 + 2 * i for i in range(n)]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        content_id = page_ids[i] + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{num} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()


def make_docx(pages: list[list[str]]) -> bytes:
    """DOCX con saltos de página explícitos entre cada lista de párrafos."""
    doc = DocxDocument()
    for i, paragraphs in enumerate(pages):
        for j, text in enumerate(paragraphs):
            p = doc.add_paragraph()
            if i > 0 and j == 0:
                p.add_run().add_break(WD_BREAK.PAGE)
            p.add_run(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
