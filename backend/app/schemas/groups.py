from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.document import Visibility
from app.models.user import UserRole


class GroupBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class GroupMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    users: list[GroupMemberRead]


class GroupMembersUpdate(BaseModel):
    """Reemplaza la lista completa de miembros (operación idempotente)."""

    user_ids: list[int]


class UserAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    groups: list[GroupBrief]


class UserAdminUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    group_ids: list[int] | None = None


class DocumentAccessUpdate(BaseModel):
    visibility: Visibility
    group_ids: list[int] = []
