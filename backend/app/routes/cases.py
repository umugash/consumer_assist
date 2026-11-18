"""Case management routes: details, timeline, evidence-gaps, escalation, and drafts."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import current_user, owned_case
from app.models import Case, GeneratedDraft
from app.schemas import (
    CaseOverview,
    CaseDetail,
    TimelineResponse,
    TimelineEventSchema,
    EvidenceGapResponse,
    EscalationRequest,
    EscalationResponse,
    DraftRequest,
    DraftResponse,
)
from app.services.timeline_evidence_engine import TimelineEngine, EvidenceEngine
from app.services.escalation_engine import EscalationEngine
from app.services.draft_generator import DraftGenerator

router = APIRouter(prefix="/api/cases", tags=["Cases"])


@router.get("/", response_model=List[CaseOverview])
def list_cases(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    """List the signed-in user's cases. Identity comes from the verified token, never the query string."""
    cases = db.query(Case).filter(Case.user_id == user["id"]).order_by(Case.created_at.desc()).all()
    return cases


@router.delete("/{case_id}")
def delete_case(case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """Delete a case and all associated cascade records."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    db.delete(case)
    db.commit()
    return {"status": "deleted", "case_id": case_id, "message": "Case removed successfully"}


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """Fetch complete case details including turns, timeline, evidence, and drafts."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return CaseDetail(
        id=case.id,
        created_at=case.created_at,
        updated_at=case.updated_at,
        status=case.status,
        workflow_stage=case.workflow_stage,
        escalation_tier=case.escalation_tier,
        platform=case.platform,
        order_id=case.order_id,
        issue_category=case.issue_category,
        amount=case.amount,
        incident_date=case.incident_date,
        customer_support_contacted=case.customer_support_contacted,
        evidence_uploaded=case.evidence_uploaded,
        resolution_sought=case.resolution_sought,
        case_readiness_score=case.case_readiness_score or 0.0,
        evidence_gap_checklist=case.evidence_gap_checklist,
        dialogue_turns=[
            {
                "id": t.id,
                "turn_number": t.turn_number,
                "role": t.role,
                "message": t.message,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "intent_detected": t.intent_detected,
                "confidence": t.confidence,
            }
            for t in case.dialogue_turns
        ],
        timeline_events=[
            {
                "id": e.id,
                "event_date": e.event_date,
                "event_type": e.event_type,
                "description": e.description,
                "source": e.source,
                "has_conflict": e.has_conflict,
                "conflict_details": e.conflict_details,
            }
            for e in case.timeline_events
        ],
        evidence_documents=[
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "upload_timestamp": d.upload_timestamp.isoformat() if d.upload_timestamp else None,
                "processing_status": d.processing_status,
                "extracted_fields": d.extracted_fields,
            }
            for d in case.evidence_documents
        ],
        escalation_history=[
            {
                "id": h.id,
                "from_tier": h.from_tier,
                "to_tier": h.to_tier,
                "from_stage": h.from_stage,
                "to_stage": h.to_stage,
                "reason": h.reason,
                "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            }
            for h in case.escalation_history
        ],
        generated_drafts=[
            {
                "id": dr.id,
                "draft_type": dr.draft_type,
                "title": dr.title,
                "tier": dr.tier,
                "generated_at": dr.generated_at.isoformat() if dr.generated_at else None,
            }
            for dr in case.generated_drafts
        ],
    )


@router.get("/{case_id}/timeline", response_model=TimelineResponse)
def get_case_timeline(case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """Reconstruct timeline, perform chronological ordering and conflict detection."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    timeline_engine = TimelineEngine()
    events = timeline_engine.build_timeline(case_id, db)
    conflicts = timeline_engine.detect_conflicts(case_id, db)

    return TimelineResponse(
        case_id=case_id,
        events=[
            TimelineEventSchema(
                id=e["id"] if isinstance(e, dict) else e.id,
                event_date=e["event_date"] if isinstance(e, dict) else e.event_date,
                event_date_normalized=e.get("event_date_normalized") if isinstance(e, dict) else getattr(e, "event_date_normalized", None),
                event_type=e["event_type"] if isinstance(e, dict) else e.event_type,
                description=e["description"] if isinstance(e, dict) else e.description,
                source=e["source"] if isinstance(e, dict) else e.source,
                has_conflict=(e.get("has_conflict") if isinstance(e, dict) else getattr(e, "has_conflict", False)) or False,
                conflict_details=e.get("conflict_details") if isinstance(e, dict) else getattr(e, "conflict_details", None),
            )
            for e in events
        ],
        conflicts=conflicts,
        total_events=len(events),
    )


@router.get("/{case_id}/evidence-gaps", response_model=EvidenceGapResponse)
def get_evidence_gaps(case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """Run evidence-gap analysis against requirements for the case's category."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    evidence_engine = EvidenceEngine()
    gap_result = evidence_engine.compute_gap_analysis(case_id, db)

    # Persist updated score on case
    case.case_readiness_score = gap_result["readiness_score"]
    case.evidence_gap_checklist = gap_result["checklist"]
    db.commit()

    return EvidenceGapResponse(
        case_id=case_id,
        issue_category=case.issue_category,
        required_evidence=gap_result["required"],
        submitted_evidence=gap_result["submitted"],
        missing_evidence=gap_result["missing"],
        readiness_score=gap_result["readiness_score"],
        checklist=gap_result["checklist"],
    )


@router.post("/{case_id}/escalate", response_model=EscalationResponse)
def escalate_case(req: EscalationRequest, case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """Advance or transition workflow stage across the 12 stages and 3 tiers."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    from app.services.dialogue_manager import DialogueManager, _EARLY_STAGES
    missing = DialogueManager()._get_missing_slots(case)
    if req.action != "set_stage" and case.workflow_stage in _EARLY_STAGES and missing:
        raise HTTPException(status_code=400, detail="Please provide these case details first: " + ", ".join(m.replace("_", " ") for m in missing))

    escalation_engine = EscalationEngine()

    if req.action == "set_stage" and req.target_stage:
        res = escalation_engine.set_stage(case_id, req.target_stage, db)
    else:
        res = escalation_engine.advance_stage(case_id, db)

    return EscalationResponse(
        case_id=case_id,
        previous_stage=res.get("previous_stage") or res.get("prev_stage") or case.workflow_stage,
        current_stage=res.get("current_stage") or case.workflow_stage,
        previous_tier=res.get("previous_tier") or res.get("prev_tier") or case.escalation_tier,
        current_tier=res.get("current_tier") or case.escalation_tier,
        allowed_next_stages=res.get("allowed_next_stages") or res.get("allowed_next") or [],
        message=res.get("message", "Stage updated successfully"),
    )


@router.post("/{case_id}/generate-draft", response_model=DraftResponse)
def generate_draft(req: DraftRequest, case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """Generate structured legal/grievance drafts grounded strictly in case evidence."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    generator = DraftGenerator()
    if req.draft_type == "nch_summary":
        draft = generator.generate_nch_summary(case_id, db)
    elif req.draft_type == "ejagriti_package":
        draft = generator.generate_ejagriti_package(case_id, db)
    else:
        draft = generator.generate_platform_email(case_id, db)

    if isinstance(draft, dict):
        return DraftResponse(
            draft_id=draft.get("draft_id", ""),
            case_id=draft.get("case_id", case_id),
            draft_type=draft.get("draft_type", req.draft_type),
            title=draft.get("title", "Statutory Complaint Draft"),
            content=draft.get("content", ""),
            tier=draft.get("tier", case.escalation_tier),
            generated_at=draft.get("generated_at") or datetime.utcnow(),
            metadata=draft.get("metadata"),
        )

    return DraftResponse(
        draft_id=draft.id,
        case_id=case_id,
        draft_type=draft.draft_type,
        title=draft.title,
        content=draft.content,
        tier=draft.tier,
        generated_at=draft.generated_at,
        metadata=draft.metadata_json,
    )


@router.get("/{case_id}/drafts")
def list_drafts(case_id: str, _owner: Case = Depends(owned_case), db: Session = Depends(get_db)):
    """List all generated drafts for the specified case."""
    drafts = db.query(GeneratedDraft).filter(GeneratedDraft.case_id == case_id).order_by(GeneratedDraft.generated_at.desc()).all()
    return [
        {
            "id": d.id,
            "draft_type": d.draft_type,
            "title": d.title,
            "content": d.content,
            "tier": d.tier,
            "generated_at": d.generated_at.isoformat() if d.generated_at else None,
            "metadata": d.metadata_json,
        }
        for d in drafts
    ]

