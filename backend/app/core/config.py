from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Career Hub"
    VERSION: str = "4.3.0"
    API_V1_STR: str = "/api/v1"
    PRODUCTION: bool = False  # Set to True via env var in production to hide /docs

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: int = 5432
    # e.g. "require" for TLS-only hosts like Neon; blank keeps the AWS RDS default
    DB_SSLMODE: str = ""

    @computed_field
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Sync URI — used by Alembic and synchronous background tasks."""
        uri = (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            "?connect_timeout=10"
        )
        if self.DB_SSLMODE:
            uri += f"&sslmode={self.DB_SSLMODE}"
        return uri

    @computed_field
    def SQLALCHEMY_ASYNC_DATABASE_URI(self) -> str:
        """Async URI — FastAPI request handlers via SQLAlchemy async engine."""
        uri = (
            f"postgresql+psycopg_async://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            "?connect_timeout=10"
        )
        if self.DB_SSLMODE:
            uri += f"&sslmode={self.DB_SSLMODE}"
        return uri

    # Redis — used for rate limiting and future caching.
    # Defaults to the Docker Compose service name; override in non-Docker environments.
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_SSL: bool = False  # True switches the Redis clients to rediss:// (e.g. Upstash)

    # AI — Ollama (local dev default)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2:3b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # AI — Groq (takes priority over Ollama when set; get a key at console.groq.com)
    GROQ_API_KEY: str = ""
    GROQ_LLM_MODEL: str = "llama-3.1-8b-instant"

    # Vector store for RAG embeddings — "chroma" (persistent local) or "qdrant" (managed)
    VECTOR_BACKEND: str = "chroma"
    CHROMA_PERSIST_DIR: str = "/app/chroma_data"
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "careerhub"

    @computed_field
    def USE_GROQ(self) -> bool:
        """True when GROQ_API_KEY is set."""
        return bool(self.GROQ_API_KEY)

    # n8n workflow orchestration (optional — falls back to local BackgroundTasks)
    N8N_WEBHOOK_URL: str = ""
    N8N_WEBHOOK_SECRET: str = ""

    @computed_field
    def N8N_ENABLED(self) -> bool:
        """True when both n8n URL and secret are configured."""
        return bool(self.N8N_WEBHOOK_URL and self.N8N_WEBHOOK_SECRET)

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BASE_URL: str = "http://localhost:8000"
    SENTRY_DSN: str = ""
    ADMIN_SECRET: str = ""  # Required to call /admin/* endpoints; set via SSM in production

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("ADMIN_SECRET")
    @classmethod
    def validate_admin_secret(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("ADMIN_SECRET must be at least 32 characters or left empty to disable")
        return v

    # comma-separated allowed CORS origins, e.g. "https://careerhub.example.com,http://localhost:8501"
    ALLOWED_ORIGINS: str = "http://localhost:8501"

    @computed_field
    def CORS_ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_ignore_empty=True,
        extra="ignore",
    )


settings = Settings()
