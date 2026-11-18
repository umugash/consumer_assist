"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from pathlib import Path
import os


# Resolve default SQLite path to absolute path in repository root
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = (_ROOT_DIR / "consumer_assist.db").as_posix()

class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite:///{_DEFAULT_DB_PATH}"
    UPLOAD_DIR: str = "/tmp/uploads" if os.environ.get("VERCEL") else "./uploads"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    DATA_DIR: str = str(Path(__file__).parent.parent.parent / "data")
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    VITE_SUPABASE_URL: str = ""
    VITE_SUPABASE_ANON_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"  # legacy name, kept for existing .env files
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_MODEL: str = "gemini-flash-lite-latest"  # gemini-1.5-* models are retired; lite is fastest + least overloaded
    LLM_TIMEOUT_SECONDS: float = 12.0

    
    model_config = {"env_file": str(_ROOT_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# Ensure upload dir exists
try:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
except Exception:
    pass


