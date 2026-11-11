"""SQLAlchemy ORM models for ConsumerAssist case management."""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, Boolean,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


# ── Enums ──────────────────────────────────────────────────────────────────

class IssueCategory(str, enum.Enum):
    NON_DELIVERY = "Non-Delivery"
    DAMAGED_DEFECTIVE = "Damaged/Defective Item"
    WRONG_MISSING = "Wrong/Missing Item"
    REFUND_DELAYED = "Refund Delayed/Denied"
    HIDDEN_CHARGES = "Hidden Charges/Overbilling"
    EXPIRED_FOOD = "Expired Food/Quick-Commerce Issue"
    OTHER = "Other"


class EscalationTier(str, enum.Enum):
    TIER_1_PLATFORM = "Tier 1: Platform Escalation"
    TIER_2_NCH = "Tier 2: National Consumer Helpline"
    TIER_3_EJAGRITI = "Tier 3: e-Jagriti Consumer Commission"


class WorkflowStage(str, enum.Enum):
    INTAKE = "1. Intake & Greeting"
    CLASSIFICATION = "2. Issue Classification"
    SLOT_FILLING = "3. Slot Filling"
    EVIDENCE_INGESTION = "4. Evidence Ingestion & OCR"
    TIMELINE_RECONSTRUCTION = "5. Timeline Reconstruction"
    CONFLICT_VERIFICATION = "6. Conflict & Gap Verification"
    TIER1_DRAFT = "7. Tier 1: Platform Grievance Routing & Draft"
    PLATFORM_TRACKING = "8. Platform SLA/Response Tracking"
    TIER2_READINESS = "9. Tier 2: NCH Readiness"
    NCH_DOCKET = "10. NCH Docket Generation"
    TIER3_CHECKLIST = "11. Tier 3: e-Jagriti Pre-Filing Checklist"
    FINAL_FILING = "12. Final Consumer Commission Filing Package"


class CaseStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING_EVIDENCE = "pending_evidence"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ── Helper ─────────────────────────────────────────────────────────────────

def generate_uuid():
    return str(uuid.uuid4())


# ── Models ─────────────────────────────────────────────────────────────────

class Case(Base):
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Case identity
    status = Column(String, default=CaseStatus.ACTIVE.value)
    workflow_stage = Column(String, default=WorkflowStage.INTAKE.value)
    escalation_tier = Column(String, default=EscalationTier.TIER_1_PLATFORM.value)
    
    # Dialogue-state slots
    platform = Column(String, nullable=True)
    order_id = Column(String, nullable=True)
    issue_category = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    incident_date = Column(String, nullable=True)
    customer_support_contacted = Column(Boolean, nullable=True)
    evidence_uploaded = Column(Boolean, default=False)
    resolution_sought = Column(String, nullable=True)
    
    # Computed scores
    case_readiness_score = Column(Float, default=0.0)
    evidence_gap_checklist = Column(JSON, nullable=True)
    
    # Relationships
    dialogue_turns = relationship("DialogueTurn", back_populates="case", cascade="all, delete-orphan")
    entities = relationship("ExtractedEntity", back_populates="case", cascade="all, delete-orphan")
    timeline_events = relationship("TimelineEvent", back_populates="case", cascade="all, delete-orphan")
    evidence_documents = relationship("EvidenceDocument", back_populates="case", cascade="all, delete-orphan")
    escalation_history = relationship("EscalationHistory", back_populates="case", cascade="all, delete-orphan")
    generated_drafts = relationship("GeneratedDraft", back_populates="case", cascade="all, delete-orphan")


class DialogueTurn(Base):
    __tablename__ = "dialogue_turns"

    id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    turn_number = Column(Integer, nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    slots_updated = Column(JSON, nullable=True)  # Which slots changed this turn
    intent_detected = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    
    case = relationship("Case", back_populates="dialogue_turns")


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    entity_type = Column(String, nullable=False)  # PLATFORM, AMOUNT, ORDER_ID, DATE, etc.
    entity_value = Column(String, nullable=False)
    normalized_value = Column(String, nullable=True)
    source = Column(String, nullable=False)  # "chat", "ocr", "document"
    source_turn_id = Column(String, nullable=True)
    confidence = Column(Float, default=1.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    case = relationship("Case", back_populates="entities")


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    event_date = Column(String, nullable=False)
    event_date_normalized = Column(DateTime, nullable=True)
    event_type = Column(String, nullable=False)  # order_placed, delivery_expected, complaint_filed, etc.
    description = Column(Text, nullable=False)
    source = Column(String, nullable=False)  # "user_reported", "ocr_extracted", "system_inferred"
    has_conflict = Column(Boolean, default=False)
    conflict_details = Column(Text, nullable=True)
    
    case = relationship("Case", back_populates="timeline_events")


class EvidenceDocument(Base):
    __tablename__ = "evidence_documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, image, screenshot
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    ocr_text = Column(Text, nullable=True)
    extracted_fields = Column(JSON, nullable=True)  # Structured data from OCR
    processing_status = Column(String, default="pending")  # pending, processed, failed
    
    case = relationship("Case", back_populates="evidence_documents")


class EscalationHistory(Base):
    __tablename__ = "escalation_history"

    id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    from_tier = Column(String, nullable=False)
    to_tier = Column(String, nullable=False)
    from_stage = Column(String, nullable=False)
    to_stage = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    case = relationship("Case", back_populates="escalation_history")


class GeneratedDraft(Base):
    __tablename__ = "generated_drafts"

    id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    draft_type = Column(String, nullable=False)  # platform_email, nch_summary, ejagriti_package
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    tier = Column(String, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)
    
    case = relationship("Case", back_populates="generated_drafts")
