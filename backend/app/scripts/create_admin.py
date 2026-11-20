"""Crea un usuario administrador (o asciende uno existente).

Uso:
    python -m app.scripts.create_admin --email admin@empresa.com --name "Admin"
    docker compose exec backend python -m app.scripts.create_admin --email ... --name ...

La contraseña se pide por consola (no queda en el historial de la shell).
"""
import argparse
import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear usuario administrador")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    email = args.email.lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.role = UserRole.ADMIN
            print(f"Usuario existente {email} ascendido a admin.")
        else:
            password = getpass.getpass("Contraseña (mín. 8 caracteres): ")
            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                raise SystemExit("La contraseña debe tener entre 8 caracteres y 72 bytes.")
            if password != getpass.getpass("Repite la contraseña: "):
                raise SystemExit("Las contraseñas no coinciden.")
            user = User(
                email=email,
                full_name=args.name,
                hashed_password=hash_password(password),
                role=UserRole.ADMIN,
            )
            db.add(user)
            print(f"Administrador {email} creado.")
        db.commit()


if __name__ == "__main__":
    main()
