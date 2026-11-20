"""Configuración centralizada: se lee de variables de entorno / archivo .env.

pydantic-settings valida tipos al arrancar, así un error de configuración
falla pronto y con un mensaje claro en vez de a mitad de una petición.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repo (…/enterprise-ai-knowledge-assistant) para encontrar el .env
ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    postgres_user: str = "kb_user"
    postgres_password: str = "kb_password"
    postgres_db: str = "knowledge_base"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60

    cors_origins: str = "http://localhost:4200"

    # --- Ingesta de documentos ---
    storage_dir: Path = ROOT_DIR / "backend" / "storage" / "documents"
    max_upload_mb: int = 20
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 80
    embedding_batch_size: int = 100

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
