"""Esquemas Pydantic: definen qué entra y qué sale de la API.

Separarlos de los modelos ORM evita, por ejemplo, devolver `hashed_password`
por accidente.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        # bcrypt solo usa los primeros 72 *bytes*; con tildes/emoji un carácter ocupa más de 1.
        if len(v.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
