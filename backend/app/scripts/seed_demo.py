"""Carga el corpus de demostración (empresa ficticia) con grupos, usuarios y documentos.

Uso (con la BD migrada y OPENAI_API_KEY en el .env):
    python -m app.scripts.seed_demo
    docker compose exec backend python -m app.scripts.seed_demo

La contraseña de los usuarios demo se pide por consola (la misma para todos).
Es idempotente: lo que ya existe (por nombre, email o título) no se duplica.
"""
import argparse
import getpass
import json
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import ROOT_DIR, get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.document import Document, DocumentStatus, FileType, Visibility
from app.models.group import Group
from app.models.user import User, UserRole
from app.services.embeddings import get_embedder
from app.services.ingestion import ingest_document

SAMPLES_DIR = ROOT_DIR / "samples"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=SAMPLES_DIR / "manifest.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    docs_dir = args.manifest.parent / "docs"
    settings = get_settings()

    with SessionLocal() as db:
        groups: dict[str, Group] = {}
        for g in manifest["groups"]:
            group = db.scalar(select(Group).where(Group.name == g["name"]))
            if group is None:
                group = Group(name=g["name"], description=g.get("description"))
                db.add(group)
                print(f"+ grupo {g['name']}")
            groups[g["name"]] = group
        db.flush()

        password = None
        for u in manifest["users"]:
            user = db.scalar(select(User).where(User.email == u["email"]))
            if user is None:
                if password is None:
                    password = getpass.getpass("Contraseña para los usuarios demo (mín. 8): ")
                    if len(password) < 8:
                        raise SystemExit("La contraseña debe tener al menos 8 caracteres.")
                user = User(
                    email=u["email"], full_name=u["full_name"],
                    hashed_password=hash_password(password), role=UserRole(u["role"]),
                )
                db.add(user)
                print(f"+ usuario {u['email']} ({u['role']})")
            user.groups = [groups[name] for name in u["groups"]]
        db.commit()

        embedder = get_embedder()
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        for d in manifest["documents"]:
            if db.scalar(select(Document).where(Document.title == d["title"])):
                print(f"= documento ya existe: {d['title']}")
                continue
            source = docs_dir / d["file"]
            file_type = FileType(source.suffix.lstrip(".").lower())
            stored = f"{uuid.uuid4().hex}.{file_type.value}"
            shutil.copyfile(source, settings.storage_dir / stored)
            document = Document(
                title=d["title"], original_filename=source.name, stored_filename=stored,
                file_type=file_type, size_bytes=source.stat().st_size,
                status=DocumentStatus.PENDING, visibility=Visibility(d["visibility"]),
                groups=[groups[name] for name in d["groups"]],
            )
            db.add(document)
            db.commit()
            ingest_document(db, document, embedder)  # síncrono: queremos ver el resultado
            print(f"+ documento {d['title']}: {document.status.value}, {document.num_chunks} chunks"
                  + (f" — {document.error}" if document.error else ""))


if __name__ == "__main__":
    main()
