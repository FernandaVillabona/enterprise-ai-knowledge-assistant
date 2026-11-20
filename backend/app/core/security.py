"""Hash de contraseñas (bcrypt) y tokens de acceso (JWT).

- Nunca guardamos la contraseña: solo su hash bcrypt, que incluye una sal aleatoria
  y es deliberadamente lento para dificultar ataques de fuerza bruta.
- El JWT es un token firmado (HS256) que el cliente envía en cada petición en la
  cabecera `Authorization: Bearer <token>`. El servidor no guarda sesiones: le
  basta con verificar la firma y la caducidad.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str | int, extra_claims: dict | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Devuelve el payload o lanza jwt.InvalidTokenError (firma mala, caducado…)."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
