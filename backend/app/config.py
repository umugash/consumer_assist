"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from pathlib import Path
import os


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./consumer_assist.db"
    UPLOAD_DIR: str = "./uploads"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    DATA_DIR: str = str(Path(__file__).parent.parent.parent / "data")
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure upload dir exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
