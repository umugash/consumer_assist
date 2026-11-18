"""ConsumerAssist API — FastAPI application entry point."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db, SessionLocal
from app.models import (
    Case, DialogueTurn, TimelineEvent,
    IssueCategory, WorkflowStage, EscalationTier, CaseStatus,
)
from app.routes import chat, cases, documents, evaluation


# ── Startup / Shutdown ─────────────────────────────────────────────────────

def _seed_sample_data():
    """Load synthetic complaints and create 3 sample cases so the dashboard
    looks populated on first launch."""
    data_path = Path(settings.DATA_DIR) / "synthetic_indian_complaints.json"
    if not data_path.exists():
        return

    db = SessionLocal()
    try:
        # Skip seeding if data already exists
        if db.query(Case).first() is not None:
            return

        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        complaints = data.get("complaints", [])[:3]  # First 3 complaints

        for complaint in complaints:
            case = Case(
                status=CaseStatus.ACTIVE.value,
                workflow_stage=WorkflowStage.SLOT_FILLING.value,
                escalation_tier=EscalationTier.TIER_1_PLATFORM.value,
                platform=complaint.get("platform"),
                order_id=complaint.get("order_id"),
                issue_category=complaint.get("issue_category"),
                amount=complaint.get("amount"),
                incident_date=complaint.get("incident_date"),
                customer_support_contacted=complaint.get("customer_support_contacted"),
                evidence_uploaded=False,
                resolution_sought=complaint.get("resolution_sought"),
                case_readiness_score=35.0,
            )
            db.add(case)
            db.flush()  # Populate case.id

            # Add dialogue turns from the synthetic data
            dialogue = complaint.get("dialogue", [])
            for idx, turn in enumerate(dialogue, start=1):
                db.add(DialogueTurn(
                    case_id=case.id,
                    turn_number=idx,
                    role=turn["role"],
                    message=turn["message"],
                    timestamp=datetime.utcnow(),
                    intent_detected=(
                        complaint.get("issue_category") if turn["role"] == "user" and idx == 1 else None
                    ),
                    confidence=0.92 if turn["role"] == "user" and idx == 1 else None,
                ))

            # Add a few timeline events from expected_timeline
            for evt in complaint.get("expected_timeline", [])[:3]:
                db.add(TimelineEvent(
                    case_id=case.id,
                    event_date=evt["date"],
                    event_type="user_reported",
                    description=evt["event"],
                    source="user_reported",
                ))

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    init_db()
    _seed_sample_data()
    yield  # Application runs here


# ── FastAPI App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="ConsumerAssist API",
    description=(
        "AI-powered Indian consumer complaint assistant with structured "
        "dialogue, NLP-based entity extraction, evidence management, "
        "escalation workflow, and draft generation for NCH / e-Jagriti filings."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────

origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────

app.include_router(chat.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(evaluation.router)

# ── Static Files (uploads) ─────────────────────────────────────────────────

try:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
except Exception:
    pass

# ── Root Endpoint ──────────────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    """Non-secret deployment diagnostics: which backends are configured (booleans only)."""
    from app.database import DB_BACKEND
    from app.services.llm_service import _get_api_keys
    from app.auth import _supabase
    openai_key, gemini_key = _get_api_keys()
    url, key = _supabase()
    return {"database": DB_BACKEND, "gemini_configured": bool(gemini_key), "gemini_model": settings.GEMINI_MODEL,
            "openai_configured": bool(openai_key), "auth_configured": bool(url and key)}


@app.get("/")
@app.get("/api")
@app.get("/api/")
async def root():
    """API information endpoint."""
    return {
        "name": "ConsumerAssist API",
        "version": "1.0.0",
        "description": (
            "AI-powered Indian consumer complaint assistant. "
            "Covers structured dialogue, NLP entity extraction, evidence "
            "management, 12-stage escalation workflow, and draft generation."
        ),
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/chat",
            "cases": "/api/cases",
            "documents": "/api/documents",
            "evaluation": "/api/evaluation",
        },
    }
