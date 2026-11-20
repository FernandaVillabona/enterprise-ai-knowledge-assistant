from sqlalchemy import func, select

from app.models.document import Chunk
from tests.factories import make_docx, make_pdf

VACATION_POLICY = (
    "Política de vacaciones\n\n"
    "Todos los empleados tienen derecho a 23 días hábiles de vacaciones al año.\n\n"
    "Las vacaciones deben solicitarse con al menos 15 días de antelación."
)


def upload(client, headers, name, content, title=None):
    data = {"title": title} if title else {}
    return client.post(
        "/api/documents", headers=headers, files={"file": (name, content)}, data=data
    )


def test_upload_txt_is_processed_into_chunks(client, admin_headers, db, storage_dir):
    r = upload(client, admin_headers, "vacaciones.txt", VACATION_POLICY.encode())
    assert r.status_code == 202
    doc_id = r.json()["id"]
    assert r.json()["title"] == "vacaciones"

    # TestClient ejecuta las BackgroundTasks antes de devolver la respuesta
    doc = client.get(f"/api/documents/{doc_id}", headers=admin_headers).json()
    assert doc["status"] == "ready", doc["error"]
    assert doc["num_pages"] == 1
    assert doc["num_chunks"] >= 1

    chunks = client.get(f"/api/documents/{doc_id}/chunks", headers=admin_headers).json()
    assert "23 días hábiles" in chunks[0]["content"]
    assert "embedding" not in chunks[0]
    assert len(list(storage_dir.iterdir())) == 1


def test_upload_pdf_and_docx_keep_page_numbers(client, admin_headers):
    pdf = upload(client, admin_headers, "p.pdf", make_pdf(["Intro", "Vacaciones 23 dias"]), "PDF")
    docx = upload(client, admin_headers, "d.docx", make_docx([["Intro"], ["Vacaciones 23 días"]]))

    for r in (pdf, docx):
        doc_id = r.json()["id"]
        doc = client.get(f"/api/documents/{doc_id}", headers=admin_headers).json()
        assert doc["status"] == "ready", doc["error"]
        assert doc["num_pages"] == 2
        chunks = client.get(f"/api/documents/{doc_id}/chunks", headers=admin_headers).json()
        assert [c["page_number"] for c in chunks] == [1, 2]


def test_regular_user_cannot_upload_or_list(client, user_headers):
    assert upload(client, user_headers, "a.txt", b"hola").status_code == 403
    assert client.get("/api/documents", headers=user_headers).status_code == 403


def test_rejects_unsupported_or_spoofed_files(client, admin_headers):
    assert upload(client, admin_headers, "foto.png", b"\x89PNG...").status_code == 415
    # Extensión .pdf pero contenido de texto: la firma no coincide
    assert upload(client, admin_headers, "falso.pdf", b"no soy un pdf").status_code == 415


def test_rejects_too_large_file(client, admin_headers, monkeypatch, storage_dir):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = b"a" * (1024 * 1024 + 1)
    assert upload(client, admin_headers, "grande.txt", big).status_code == 413
    assert not storage_dir.exists() or not any(storage_dir.iterdir())


def test_document_without_text_is_marked_failed(client, admin_headers):
    r = upload(client, admin_headers, "vacio.txt", b"   \n  ")
    doc = client.get(f"/api/documents/{r.json()['id']}", headers=admin_headers).json()
    assert doc["status"] == "failed"
    assert "No se encontró texto" in doc["error"]


def test_reprocess_replaces_chunks(client, admin_headers, db):
    doc_id = upload(client, admin_headers, "v.txt", VACATION_POLICY.encode()).json()["id"]
    first = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id))

    r = client.post(f"/api/documents/{doc_id}/reprocess", headers=admin_headers)
    assert r.status_code == 202
    again = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id))
    assert again == first


def test_delete_removes_document_chunks_and_file(client, admin_headers, db, storage_dir):
    doc_id = upload(client, admin_headers, "v.txt", VACATION_POLICY.encode()).json()["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=admin_headers).status_code == 204

    assert client.get(f"/api/documents/{doc_id}", headers=admin_headers).status_code == 404
    assert db.scalar(select(func.count()).select_from(Chunk)) == 0
    assert not any(storage_dir.iterdir())
