from fastapi import Depends
from fastapi.testclient import TestClient

from app.api.deps import require_admin
from app.core.security import create_access_token
from app.main import app


def register(client: TestClient, email="ana@empresa.com", password="secreto-123"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "full_name": "Ana", "password": password},
    )


def login(client: TestClient, email="ana@empresa.com", password="secreto-123"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_register_creates_regular_user_without_exposing_password(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "ana@empresa.com"
    assert body["role"] == "user"
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email_is_rejected_case_insensitive(client):
    register(client)
    r = register(client, email="ANA@empresa.com")
    assert r.status_code == 409


def test_register_validates_input(client):
    assert register(client, email="no-es-email").status_code == 422
    assert register(client, password="corta").status_code == 422
    assert register(client, password="ñ" * 40).status_code == 422  # 80 bytes > 72


def test_login_and_me(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ana@empresa.com"


def test_login_wrong_password_and_unknown_email_give_same_error(client):
    register(client)
    bad_pass = login(client, password="incorrecta")
    unknown = login(client, email="nadie@empresa.com")
    assert bad_pass.status_code == unknown.status_code == 401
    assert bad_pass.json() == unknown.json()


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401


def test_token_for_deleted_user_is_rejected(client):
    token = create_access_token(9999)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_require_admin(client, admin_user):
    # Ruta temporal solo para el test
    @app.get("/api/_admin-only")
    def _admin_only(_=Depends(require_admin)):
        return {"ok": True}

    try:
        register(client)
        user_token = login(client).json()["access_token"]
        admin_token = login(client, "admin@empresa.com", "password-123").json()["access_token"]

        r_user = client.get("/api/_admin-only", headers={"Authorization": f"Bearer {user_token}"})
        r_admin = client.get("/api/_admin-only", headers={"Authorization": f"Bearer {admin_token}"})
        assert r_user.status_code == 403
        assert r_admin.status_code == 200
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/api/_admin-only"]
