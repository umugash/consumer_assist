"""Chat / dialogue endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Case, DialogueTurn, CaseStatus, WorkflowStage, EscalationTier
from app.schemas import ChatRequest, ChatResponse, SlotState
from app.services.dialogue_manager import DialogueManager

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/send", response_model=ChatResponse)
async def send_message(req: ChatRequest, db: Session = Depends(get_db)):
    """Process a user message. Creates a new case when ``case_id`` is absent."""

    # Resolve or create case
    if req.case_id:
        case = db.query(Case).filter(Case.id == req.case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
    else:
        case = Case(
            user_id=req.user_id,
            user_email=req.user_email,
            status=CaseStatus.ACTIVE.value,
            workflow_stage=WorkflowStage.INTAKE.value,
            escalation_tier=EscalationTier.TIER_1_PLATFORM.value,
        )
        db.add(case)
        db.commit()
        db.refresh(case)

    # If case exists but user_id was not set, backfill it
    if req.user_id and not case.user_id:
        case.user_id = req.user_id
        case.user_email = req.user_email
        db.commit()

    # Dialogue processing with graceful error fallback
    dm = DialogueManager()
    try:
        result = dm.process_message(case, req.message, db)
    except Exception as err:
        import logging
        logging.getLogger(__name__).error(f"Error in dialogue processing: {err}", exc_info=True)
        # Ensure database is in a consistent state
        db.rollback()
        # Fallback graceful 200 response
        fallback_msg = (
            "I couldn't quite understand that format. Could you please rephrase or specify the details "
            "(e.g., date as YYYY-MM-DD or disputed amount in ₹)?"
        )
        result = {
            "turn_number": len(case.dialogue_turns) + 1 if case.dialogue_turns else 1,
            "assistant_message": fallback_msg,
            "missing_slots": dm._get_missing_slots(case),
            "intent": case.issue_category or "Other",
            "confidence": 0.5,
            "entities_extracted": [],
        }

    # Build response
    slots = SlotState(
        platform=case.platform,
        order_id=case.order_id,
        issue_category=case.issue_category,
        amount=case.amount,
        incident_date=case.incident_date,
        customer_support_contacted=case.customer_support_contacted,
        evidence_uploaded=case.evidence_uploaded,
        resolution_sought=case.resolution_sought,
    )

    return ChatResponse(
        case_id=case.id,
        turn_number=result.get("turn_number", 1),
        assistant_message=result.get("assistant_message", ""),
        slots=slots,
        missing_slots=result.get("missing_slots", []),
        intent_detected=result.get("intent"),
        confidence=result.get("confidence"),
        workflow_stage=case.workflow_stage,
        escalation_tier=case.escalation_tier,
        entities_extracted=result.get("entities_extracted", []),
    )


@router.get("/history/{case_id}")
async def get_chat_history(case_id: str, db: Session = Depends(get_db)):
    """Return all dialogue turns for a case, ordered by turn number."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    turns = (
        db.query(DialogueTurn)
        .filter(DialogueTurn.case_id == case_id)
        .order_by(DialogueTurn.turn_number)
        .all()
    )

    return {
        "case_id": case_id,
        "turns": [
            {
                "id": t.id,
                "turn_number": t.turn_number,
                "role": t.role,
                "message": t.message,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "slots_updated": t.slots_updated,
                "intent_detected": t.intent_detected,
                "confidence": t.confidence,
            }
            for t in turns
        ],
        "total_turns": len(turns),
    }
