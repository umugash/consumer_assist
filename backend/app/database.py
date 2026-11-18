"""Database connection and session management."""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings, _DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

def _create_engine():
    db_url = settings.DATABASE_URL
    if db_url and not db_url.startswith("sqlite"):
        if db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
            try:
                import psycopg2  # noqa: F401
                driver = "psycopg2"
            except ImportError:
                driver = "psycopg"  # psycopg v3 is what requirements.txt installs on Vercel
            db_url = db_url.replace("postgresql://", f"postgresql+{driver}://", 1)
        try:
            eng = create_engine(
                db_url,
                connect_args={"connect_timeout": 3},
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False,
            )
            with eng.connect() as conn:
                pass
            logger.info("Successfully connected to PostgreSQL/Supabase database.")
            return eng
        except Exception as exc:
            logger.error(f"PostgreSQL connection failed ({type(exc).__name__}). Falling back to EPHEMERAL SQLite - data will not persist.")

    # SQLite fallback
    sqlite_path = "/tmp/consumer_assist.db" if (os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")) else _DEFAULT_DB_PATH
    return create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )

engine = _create_engine()
DB_BACKEND = engine.dialect.name  # surfaced by /api/health
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    try:
        from app.models import (
            Case, DialogueTurn, ExtractedEntity, TimelineEvent,
            EvidenceDocument, EscalationHistory, GeneratedDraft
        )
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"Database init skipped or already exists: {exc}")

