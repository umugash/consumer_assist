"""Pydantic schemas for API request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ── Chat / Dialogue ────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    case_id: Optional[str] = None
    message: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    

class SlotState(BaseModel):
    platform: Optional[str] = None
    order_id: Optional[str] = None
    issue_category: Optional[str] = None
    amount: Optional[float] = None
    incident_date: Optional[str] = None
    customer_support_contacted: Optional[bool] = None
    evidence_uploaded: bool = False
    resolution_sought: Optional[str] = None
    

class ChatResponse(BaseModel):
    case_id: str
    turn_number: int
    assistant_message: str
    slots: SlotState
    missing_slots: List[str]
    intent_detected: Optional[str] = None
    confidence: Optional[float] = None
    workflow_stage: str
    escalation_tier: str
    entities_extracted: List[Dict[str, Any]] = []


# ── Case ───────────────────────────────────────────────────────────────────

class CaseOverview(BaseModel):
    id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status: str
    workflow_stage: str
    escalation_tier: str
    platform: Optional[str] = None
    order_id: Optional[str] = None
    issue_category: Optional[str] = None
    amount: Optional[float] = None
    incident_date: Optional[str] = None
    customer_support_contacted: Optional[bool] = None
    evidence_uploaded: bool = False
    resolution_sought: Optional[str] = None
    case_readiness_score: float = 0.0
    evidence_gap_checklist: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class CaseDetail(CaseOverview):
    dialogue_turns: List[Dict[str, Any]] = []
    timeline_events: List[Dict[str, Any]] = []
    evidence_documents: List[Dict[str, Any]] = []
    escalation_history: List[Dict[str, Any]] = []
    generated_drafts: List[Dict[str, Any]] = []


# ── Document Upload ────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    processing_status: str
    ocr_text: Optional[str] = None
    extracted_fields: Optional[Dict[str, Any]] = None
    categorized_as: Optional[str] = None
    assistant_message: Optional[str] = None
    readiness_score: Optional[float] = None
    checklist: Optional[Dict[str, bool]] = None


# ── Timeline ──────────────────────────────────────────────────────────────

class TimelineEventSchema(BaseModel):
    id: str
    event_date: str
    event_date_normalized: Optional[datetime] = None
    event_type: str
    description: str
    source: str
    has_conflict: bool = False
    conflict_details: Optional[str] = None

    class Config:
        from_attributes = True


class TimelineResponse(BaseModel):
    case_id: str
    events: List[TimelineEventSchema]
    conflicts: List[Dict[str, Any]]
    total_events: int


# ── Evidence ──────────────────────────────────────────────────────────────

class EvidenceGapResponse(BaseModel):
    case_id: str
    issue_category: Optional[str]
    required_evidence: List[str]
    submitted_evidence: List[str]
    missing_evidence: List[str]
    readiness_score: float
    checklist: Dict[str, bool]


# ── Escalation ────────────────────────────────────────────────────────────

class EscalationRequest(BaseModel):
    case_id: str
    action: str = "advance"  # "advance" or "set_stage"
    target_stage: Optional[str] = None


class EscalationResponse(BaseModel):
    case_id: str
    previous_stage: str
    current_stage: str
    previous_tier: str
    current_tier: str
    allowed_next_stages: List[str]
    message: str


# ── Draft Generation ─────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    case_id: str
    draft_type: str  # "platform_email", "nch_summary", "ejagriti_package"


class DraftResponse(BaseModel):
    draft_id: str
    case_id: str
    draft_type: str
    title: str
    content: str
    tier: str
    generated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


# ── Evaluation Metrics ───────────────────────────────────────────────────

class EvaluationMetrics(BaseModel):
    nlp_pipeline: Dict[str, Any]
    dialogue_quality: Dict[str, Any]
    retrieval_trust: Dict[str, Any]
    comparison: Dict[str, Any]  # structured_workflow vs plain_llm_baseline


# ── Knowledge Base ───────────────────────────────────────────────────────

class KBQueryRequest(BaseModel):
    query: str
    top_k: int = 3


class KBQueryResponse(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    sources: List[str]

