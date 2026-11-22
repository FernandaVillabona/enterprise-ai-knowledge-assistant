"""Tests de control de acceso.

Escenario: tres documentos
  - «Manual del empleado»   público
  - «Nóminas 2026»          restringido al grupo RR. HH.
  - «Plan de despidos»      restringido y SIN grupos (solo admins)
y dos usuarios: Rita (de RR. HH.) y Óscar (de ningún grupo).
"""
import pytest

from app.api.deps import embedder_dependency, llm_dependency, retriever_dependency
from app.core.security import create_access_token
from app.main import app
from app.models.user import User, UserRole
from app.services.llm import FakeLLM
from app.services.rag import NO_INFO_ANSWER, REWRITE_PROMPT
from app.services.search import SearchHit
from tests.conftest import _make_user
from tests.test_search import TopicEmbedder


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def upload(client, headers, title, content, visibility="restricted", group_ids=()):
    r = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("doc.txt", content.encode())},
        data={"title": title, "visibility": visibility, "group_ids": [str(g) for g in group_ids]},
    )
    assert r.status_code == 202, r.text
    return r.json()


@pytest.fixture
def world(client, db, admin_headers):
    hr = client.post("/api/groups", headers=admin_headers, json={"name": "RR. HH."}).json()
    rita = _make_user(db, "rita@empresa.com", UserRole.USER)
    oscar = _make_user(db, "oscar@empresa.com", UserRole.USER)
    client.put(f"/api/groups/{hr['id']}/members", headers=admin_headers, json={"user_ids": [rita.id]})

    docs = {
        "manual": upload(client, admin_headers, "Manual del empleado",
                         "Horario de oficina de 9 a 18 horas. Vacaciones: 23 días de descanso.", "public"),
        "nominas": upload(client, admin_headers, "Nóminas 2026",
                          "Salario base del puesto senior: 52.000 euros. Vacaciones extra de descanso.",
                          group_ids=[hr["id"]]),
        "despidos": upload(client, admin_headers, "Plan de despidos",
                           "Confidencial: reestructuración prevista en marzo. Descanso no aplica."),
    }
    return {"hr": hr, "rita": rita, "oscar": oscar, "docs": docs}


def accessible_titles(client, headers) -> set[str]:
    r = client.get("/api/documents/accessible", headers=headers)
    assert r.status_code == 200
    return {d["title"] for d in r.json()}


# ---------- Visibilidad de documentos ----------

def test_each_user_sees_only_authorized_documents(client, admin_headers, world):
    assert accessible_titles(client, auth(world["oscar"])) == {"Manual del empleado"}
    assert accessible_titles(client, auth(world["rita"])) == {"Manual del empleado", "Nóminas 2026"}
    assert accessible_titles(client, admin_headers) == {
        "Manual del empleado", "Nóminas 2026", "Plan de despidos",
    }


def test_documents_are_restricted_by_default(client, admin_headers, world):
    doc = world["docs"]["despidos"]
    assert doc["visibility"] == "restricted" and doc["groups"] == []


def test_user_summary_hides_internal_fields(client, world):
    doc = client.get("/api/documents/accessible", headers=auth(world["oscar"])).json()[0]
    assert set(doc) == {"id", "title", "file_type", "num_pages", "processed_at"}


def test_changing_access_takes_effect_immediately(client, admin_headers, world):
    doc_id = world["docs"]["despidos"]["id"]
    r = client.put(
        f"/api/documents/{doc_id}/access", headers=admin_headers,
        json={"visibility": "restricted", "group_ids": [world["hr"]["id"]]},
    )
    assert r.status_code == 200
    assert [g["name"] for g in r.json()["groups"]] == ["RR. HH."]
    assert "Plan de despidos" in accessible_titles(client, auth(world["rita"]))
    assert "Plan de despidos" not in accessible_titles(client, auth(world["oscar"]))

    client.put(f"/api/documents/{doc_id}/access", headers=admin_headers,
               json={"visibility": "public", "group_ids": []})
    assert "Plan de despidos" in accessible_titles(client, auth(world["oscar"]))


def test_removing_member_or_group_revokes_access(client, admin_headers, world):
    rita = auth(world["rita"])
    client.put(f"/api/groups/{world['hr']['id']}/members", headers=admin_headers, json={"user_ids": []})
    assert accessible_titles(client, rita) == {"Manual del empleado"}

    client.put(f"/api/groups/{world['hr']['id']}/members", headers=admin_headers,
               json={"user_ids": [world["rita"].id]})
    assert "Nóminas 2026" in accessible_titles(client, rita)
    assert client.delete(f"/api/groups/{world['hr']['id']}", headers=admin_headers).status_code == 204
    assert accessible_titles(client, rita) == {"Manual del empleado"}


def test_upload_with_unknown_group_fails_without_storing(client, admin_headers, storage_dir):
    r = client.post(
        "/api/documents", headers=admin_headers,
        files={"file": ("a.txt", b"hola")}, data={"group_ids": ["999"]},
    )
    assert r.status_code == 422
    assert not storage_dir.exists() or not any(storage_dir.iterdir())


# ---------- Administración de grupos y usuarios ----------

def test_admin_endpoints_require_admin(client, world):
    oscar = auth(world["oscar"])
    doc_id = world["docs"]["manual"]["id"]
    assert client.get("/api/groups", headers=oscar).status_code == 403
    assert client.post("/api/groups", headers=oscar, json={"name": "x"}).status_code == 403
    assert client.get("/api/users", headers=oscar).status_code == 403
    assert client.patch(f"/api/users/{world['oscar'].id}", headers=oscar,
                        json={"role": "admin"}).status_code == 403
    assert client.put(f"/api/documents/{doc_id}/access", headers=oscar,
                      json={"visibility": "public"}).status_code == 403


def test_group_validation(client, admin_headers, world):
    assert client.post("/api/groups", headers=admin_headers, json={"name": "RR. HH."}).status_code == 409
    r = client.put(f"/api/groups/{world['hr']['id']}/members", headers=admin_headers, json={"user_ids": [999]})
    assert r.status_code == 422


def test_admin_manages_user_groups_and_status(client, admin_headers, world):
    oscar_id = world["oscar"].id
    r = client.patch(f"/api/users/{oscar_id}", headers=admin_headers, json={"group_ids": [world["hr"]["id"]]})
    assert [g["name"] for g in r.json()["groups"]] == ["RR. HH."]
    assert "Nóminas 2026" in accessible_titles(client, auth(world["oscar"]))

    client.patch(f"/api/users/{oscar_id}", headers=admin_headers, json={"is_active": False})
    assert client.get("/api/documents/accessible", headers=auth(world["oscar"])).status_code == 401


def test_admin_cannot_lock_themselves_out(client, admin_headers, admin_user):
    for body in ({"role": "user"}, {"is_active": False}):
        r = client.patch(f"/api/users/{admin_user.id}", headers=admin_headers, json=body)
        assert r.status_code == 400


# ---------- Historial de chat tras perder acceso ----------

def test_revoked_sources_are_hidden_from_history_and_llm_context(client, admin_headers, world):
    payroll_id = world["docs"]["nominas"]["id"]
    hit = SearchHit(1, payroll_id, "Nóminas 2026", 1, "Salario base: 52.000 euros.", 0.03, 0.9)
    llm = FakeLLM(lambda m: "consulta" if m[0].content == REWRITE_PROMPT else "Son 52.000 euros [1].")
    app.dependency_overrides[llm_dependency] = lambda: llm
    app.dependency_overrides[retriever_dependency] = lambda: (lambda q, k: [hit])

    rita = auth(world["rita"])
    conv = client.post("/api/conversations", headers=rita, json={}).json()["id"]
    client.post(f"/api/conversations/{conv}/messages", headers=rita, json={"content": "¿Salario senior?"})

    # Rita sale de RR. HH.
    client.put(f"/api/groups/{world['hr']['id']}/members", headers=admin_headers, json={"user_ids": []})

    messages = client.get(f"/api/conversations/{conv}", headers=rita).json()["messages"]
    assert messages[1]["sources"] == []  # el fragmento de nóminas ya no se devuelve

    app.dependency_overrides[retriever_dependency] = lambda: (lambda q, k: [])
    client.post(f"/api/conversations/{conv}/messages", headers=rita, json={"content": "¿Y el junior?"})
    # Última llamada = reescritura con historial (sin fuentes no hay llamada de respuesta).
    # Conserva la pregunta de Rita, pero NO la respuesta basada en nóminas.
    rewrite_prompt = llm.calls[-1][1].content
    assert "¿Salario senior?" in rewrite_prompt
    assert "52.000" not in rewrite_prompt


# ---------- Búsqueda y chat reales (PostgreSQL) ----------

@pytest.fixture
def topic_embedder(client):
    app.dependency_overrides[embedder_dependency] = lambda: TopicEmbedder()


@pytest.fixture
def pg_world(topic_embedder, world):
    """`topic_embedder` va primero: los documentos se indexan ya con vectores con significado."""
    return world


def search_titles(client, headers, query, mode="hybrid") -> list[str]:
    r = client.post("/api/search", headers=headers, json={"query": query, "mode": mode, "top_k": 10})
    assert r.status_code == 200
    return [h["document_title"] for h in r.json()["results"]]


@pytest.mark.postgres
def test_search_never_returns_unauthorized_chunks(client, admin_headers, pg_world):
    for mode in ("semantic", "keyword", "hybrid"):
        oscar = set(search_titles(client, auth(pg_world["oscar"]), "descanso", mode))
        rita = set(search_titles(client, auth(pg_world["rita"]), "descanso", mode))
        admin = set(search_titles(client, admin_headers, "descanso", mode))
        assert oscar <= {"Manual del empleado"}, mode
        assert rita <= {"Manual del empleado", "Nóminas 2026"}, mode
        assert "Plan de despidos" in admin, mode

    assert search_titles(client, auth(pg_world["oscar"]), "salario 52.000", "keyword") == []
    assert search_titles(client, auth(pg_world["rita"]), "salario 52.000", "keyword") == ["Nóminas 2026"]


@pytest.mark.postgres
def test_chat_cannot_leak_restricted_content(client, pg_world):
    llm = FakeLLM(lambda m: "consulta" if m[0].content == REWRITE_PROMPT else "Respuesta [1].")
    app.dependency_overrides[llm_dependency] = lambda: llm

    oscar = auth(pg_world["oscar"])
    conv = client.post("/api/conversations", headers=oscar, json={}).json()["id"]
    body = client.post(
        f"/api/conversations/{conv}/messages", headers=oscar,
        json={"content": "reestructuración prevista"},
    ).json()

    # Óscar no tiene acceso al único documento que habla de reestructuración
    assert body["assistant_message"]["content"] == NO_INFO_ANSWER
    prompts = " ".join(m.content for call in llm.calls for m in call)
    assert "reestructuración prevista en marzo" not in prompts
    assert "52.000" not in prompts
