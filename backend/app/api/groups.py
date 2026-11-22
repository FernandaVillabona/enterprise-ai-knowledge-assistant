"""Administración de grupos y de usuarios (solo administradores)."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AdminUser, DbSession
from app.models.group import Group
from app.models.user import User, UserRole
from app.schemas.groups import (
    GroupCreate,
    GroupMembersUpdate,
    GroupRead,
    GroupUpdate,
    UserAdminRead,
    UserAdminUpdate,
)

groups_router = APIRouter(prefix="/groups", tags=["admin: groups"])
users_router = APIRouter(prefix="/users", tags=["admin: users"])


def resolve_groups(db: Session, group_ids: list[int]) -> list[Group]:
    """Carga los grupos pedidos; 422 si alguno no existe (mejor fallar que ignorarlo)."""
    ids = set(group_ids)
    groups = list(db.scalars(select(Group).where(Group.id.in_(ids)))) if ids else []
    missing = ids - {g.id for g in groups}
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Grupos inexistentes: {sorted(missing)}")
    return groups


def _resolve_users(db: Session, user_ids: list[int]) -> list[User]:
    ids = set(user_ids)
    users = list(db.scalars(select(User).where(User.id.in_(ids)))) if ids else []
    missing = ids - {u.id for u in users}
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Usuarios inexistentes: {sorted(missing)}")
    return users


def _get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grupo no encontrado")
    return group


def _ensure_unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    q = select(Group.id).where(Group.name == name)
    if exclude_id is not None:
        q = q.where(Group.id != exclude_id)
    if db.scalar(q):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un grupo con ese nombre")


# ---------- Grupos ----------

@groups_router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(data: GroupCreate, _: AdminUser, db: DbSession) -> Group:
    name = data.name.strip()
    _ensure_unique_name(db, name)
    group = Group(name=name, description=data.description)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@groups_router.get("", response_model=list[GroupRead])
def list_groups(_: AdminUser, db: DbSession) -> list[Group]:
    return list(db.scalars(select(Group).order_by(Group.name)))


@groups_router.patch("/{group_id}", response_model=GroupRead)
def update_group(group_id: int, data: GroupUpdate, _: AdminUser, db: DbSession) -> Group:
    group = _get_group(db, group_id)
    if data.name is not None:
        _ensure_unique_name(db, data.name.strip(), exclude_id=group.id)
        group.name = data.name.strip()
    if data.description is not None:
        group.description = data.description
    db.commit()
    db.refresh(group)
    return group


@groups_router.put("/{group_id}/members", response_model=GroupRead)
def set_group_members(group_id: int, data: GroupMembersUpdate, _: AdminUser, db: DbSession) -> Group:
    group = _get_group(db, group_id)
    group.users = _resolve_users(db, data.user_ids)
    db.commit()
    db.refresh(group)
    return group


@groups_router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, _: AdminUser, db: DbSession) -> None:
    """Borra el grupo. Sus documentos restringidos dejan de ser visibles para sus
    antiguos miembros (salvo que compartan otro grupo): de nuevo, denegar por defecto."""
    db.delete(_get_group(db, group_id))
    db.commit()


# ---------- Usuarios ----------

@users_router.get("", response_model=list[UserAdminRead])
def list_users(_: AdminUser, db: DbSession) -> list[User]:
    return list(db.scalars(select(User).order_by(User.email)))


@users_router.patch("/{user_id}", response_model=UserAdminRead)
def update_user(user_id: int, data: UserAdminUpdate, admin: AdminUser, db: DbSession) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    # Un admin no puede quitarse el rol ni desactivarse: evita quedarse sin administradores
    if user.id == admin.id and (
        (data.role is not None and data.role != UserRole.ADMIN) or data.is_active is False
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes quitarte el rol de admin ni desactivarte")

    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.group_ids is not None:
        user.groups = resolve_groups(db, data.group_ids)
    db.commit()
    db.refresh(user)
    return user
