import pytest

from app.models.document import FileType
from app.services.chunking import chunk_pages, count_tokens
from app.services.extraction import ExtractionError, Page, clean_text, extract_pages
from tests.factories import make_docx, make_pdf


# ---------- Extracción ----------

def test_pdf_pages_are_numbered(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(make_pdf(["Politica de vacaciones", "Son 23 dias habiles"]))
    pages = extract_pages(path, FileType.PDF)
    assert [p.number for p in pages] == [1, 2]
    assert "vacaciones" in pages[0].text
    assert "23 dias" in pages[1].text


def test_docx_splits_on_page_breaks(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(make_docx([["Introducción"], ["Vacaciones: 23 días", "Se piden con 15 días"]]))
    pages = extract_pages(path, FileType.DOCX)
    assert len(pages) == 2
    assert pages[0].text == "Introducción"
    assert "23 días" in pages[1].text and "15 días" in pages[1].text


def test_txt_form_feed_and_encoding_fallback(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes("página uno\fpágina dos".encode("latin-1"))
    pages = extract_pages(path, FileType.TXT)
    assert [p.text for p in pages] == ["página uno", "página dos"]


def test_empty_document_raises(tmp_path):
    path = tmp_path / "vacio.txt"
    path.write_text("   \n\n  ")
    with pytest.raises(ExtractionError):
        extract_pages(path, FileType.TXT)


def test_clean_text():
    assert clean_text("vaca-\nciones\x00  con   espacios\n\n\n\nfin") == "vacaciones con espacios\n\nfin"


# ---------- Chunking ----------

def test_short_page_is_single_chunk():
    chunks = chunk_pages([Page(1, "Texto corto.")], max_tokens=100, overlap_tokens=10)
    assert len(chunks) == 1
    assert chunks[0].page_number == 1


def test_chunks_respect_max_tokens_and_never_cross_pages():
    paragraph = "Esta es una frase de ejemplo sobre la política de la empresa. " * 20
    pages = [Page(1, "\n\n".join([paragraph] * 5)), Page(2, paragraph)]
    chunks = chunk_pages(pages, max_tokens=200, overlap_tokens=30)

    assert all(c.token_count <= 200 for c in chunks)
    assert {c.page_number for c in chunks} == {1, 2}
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Ningún chunk de la página 2 contiene texto exclusivo de la 1 y viceversa
    assert all(c.page_number == 2 for c in chunks if c.chunk_index >= len(chunks) - 1)


def test_overlap_repeats_end_of_previous_chunk():
    sentences = [f"Frase número {i} del documento." for i in range(60)]
    chunks = chunk_pages([Page(1, " ".join(sentences))], max_tokens=60, overlap_tokens=20)
    assert len(chunks) > 2
    for prev, nxt in zip(chunks, chunks[1:]):
        # El siguiente chunk empieza repitiendo una o varias frases finales del anterior
        first_sentence_next = nxt.content.split(".", 1)[0] + "."
        last_sentence_prev = "Frase" + prev.content.rsplit("Frase", 1)[-1]
        assert first_sentence_next in prev.content
        assert last_sentence_prev in nxt.content


def test_sentences_of_one_paragraph_stay_in_one_paragraph():
    long_paragraph = " ".join(f"Frase {i} de un párrafo largo." for i in range(80))
    chunks = chunk_pages([Page(1, long_paragraph)], max_tokens=60, overlap_tokens=0)
    assert all("\n\n" not in c.content for c in chunks)


def test_huge_sentence_is_hard_split():
    text = "palabra " * 1000  # sin puntuación
    chunks = chunk_pages([Page(1, text)], max_tokens=100, overlap_tokens=0)
    assert len(chunks) >= 10
    assert all(count_tokens(c.content) <= 101 for c in chunks)  # ±1 por re-tokenizar


def test_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_pages([Page(1, "x")], max_tokens=10, overlap_tokens=10)
