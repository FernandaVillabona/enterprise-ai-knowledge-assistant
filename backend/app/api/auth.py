from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DbSession) -> User:
    """Registro público. Siempre crea usuarios con rol `user`.

    Los administradores se crean con `python -m app.scripts.create_admin`, así nadie
    puede auto-asignarse privilegios desde la API.
    """
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email")

    user = User(
        email=email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=UserRole.USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    """Login estilo OAuth2 (form-data con `username` = email y `password`).

    Usamos este formato para que el botón "Authorize" de Swagger funcione directamente.
    """
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    # Mismo mensaje para "no existe" y "contraseña mala": no revelamos qué emails existen
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario desactivado")

    return Token(access_token=create_access_token(user.id, {"role": user.role.value}))


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
