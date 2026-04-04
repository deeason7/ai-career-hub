from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Career Hub"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    PRODUCTION: bool = False  # Set to True via env var in production to hide /docs

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: int = 5432

    @computed_field
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Sync URI — used by Alembic and synchronous background tasks."""
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    def SQLALCHEMY_ASYNC_DATABASE_URI(self) -> str:
        """Async URI — FastAPI request handlers via SQLAlchemy async engine."""
        return (
            f"postgresql+psycopg_async://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis & Celery
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""  # Set when Redis requires auth; empty for local/EC2 Docker Redis

    @computed_field
    def CELERY_BROKER_URL(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @computed_field
    def CELERY_RESULT_BACKEND(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/1"

    # AI — Ollama (local dev default)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2:1b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # AI — Groq (free cloud alternative; takes priority over Ollama when set)
    # Get a free key at: https://console.groq.com
    GROQ_API_KEY: str = ""
    GROQ_LLM_MODEL: str = "llama-3.1-8b-instant"

    @computed_field
    def USE_GROQ(self) -> bool:
        """True when GROQ_API_KEY is configured — used in cloud deployments."""
        return bool(self.GROQ_API_KEY)

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    SENTRY_DSN: str = ""  # Optional — set to enable error tracking

    # CORS — comma-separated list of allowed origins.
    # Locally defaults to Streamlit dev server; in production set via env/SSM.
    # Example: "https://careerhub.deeason.com.np,http://localhost:8501"
    ALLOWED_ORIGINS: str = "http://localhost:8501"

    @computed_field
    def CORS_ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # Storage
    S3_BUCKET: str = ""  # Set in production via env/SSM

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_ignore_empty=True,
        extra="ignore",
    )


settings = Settings()
