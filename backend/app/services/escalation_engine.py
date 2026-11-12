"""12-stage escalation state machine across 3 tiers for ConsumerAssist."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import (
    Case, EscalationHistory, EvidenceDocument,
    EscalationTier, WorkflowStage,
)

logger = logging.getLogger(__name__)

# ── Stage ordering ─────────────────────────────────────────────────────────

STAGE_ORDER: List[WorkflowStage] = [
    WorkflowStage.INTAKE,               # 1
    WorkflowStage.CLASSIFICATION,        # 2
    WorkflowStage.SLOT_FILLING,          # 3
    WorkflowStage.EVIDENCE_INGESTION,    # 4
    WorkflowStage.TIMELINE_RECONSTRUCTION,  # 5
    WorkflowStage.CONFLICT_VERIFICATION,    # 6
    WorkflowStage.TIER1_DRAFT,           # 7
    WorkflowStage.PLATFORM_TRACKING,     # 8
    WorkflowStage.TIER2_READINESS,       # 9
    WorkflowStage.NCH_DOCKET,           # 10
    WorkflowStage.TIER3_CHECKLIST,       # 11
    WorkflowStage.FINAL_FILING,          # 12
]

# Map from stage → tier
TIER_MAP: Dict[WorkflowStage, EscalationTier] = {
    WorkflowStage.INTAKE:                  EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.CLASSIFICATION:          EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.SLOT_FILLING:            EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.EVIDENCE_INGESTION:      EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.TIMELINE_RECONSTRUCTION: EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.CONFLICT_VERIFICATION:   EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.TIER1_DRAFT:             EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.PLATFORM_TRACKING:       EscalationTier.TIER_1_PLATFORM,
    WorkflowStage.TIER2_READINESS:         EscalationTier.TIER_2_NCH,
    WorkflowStage.NCH_DOCKET:             EscalationTier.TIER_2_NCH,
    WorkflowStage.TIER3_CHECKLIST:         EscalationTier.TIER_3_EJAGRITI,
    WorkflowStage.FINAL_FILING:            EscalationTier.TIER_3_EJAGRITI,
}

# Human-readable stage descriptions
_STAGE_INFO: Dict[WorkflowStage, Dict[str, Any]] = {
    WorkflowStage.INTAKE: {
        "description": "Initial greeting and case creation.",
        "prerequisites": [],
        "next_actions": ["Classify the consumer issue."],
    },
    WorkflowStage.CLASSIFICATION: {
        "description": "Classify the consumer complaint into a specific issue category.",
        "prerequisites": ["User has described their issue."],
        "next_actions": ["Begin collecting required case details."],
    },
    WorkflowStage.SLOT_FILLING: {
        "description": "Gather all required case details: platform, order ID, amount, dates, resolution sought.",
        "prerequisites": ["Issue category identified."],
        "next_actions": ["Upload supporting evidence."],
    },
    WorkflowStage.EVIDENCE_INGESTION: {
        "description": "Upload and process supporting documents (screenshots, invoices, receipts).",
        "prerequisites": ["All required case slots filled."],
        "next_actions": ["Build the case timeline."],
    },
    WorkflowStage.TIMELINE_RECONSTRUCTION: {
        "description": "Reconstruct a chronological timeline from user statements and OCR data.",
        "prerequisites": ["Evidence documents uploaded and processed."],
        "next_actions": ["Verify timeline for conflicts and gaps."],
    },
    WorkflowStage.CONFLICT_VERIFICATION: {
        "description": "Verify the timeline for date/amount conflicts between user claims and evidence.",
        "prerequisites": ["Timeline built."],
        "next_actions": ["Generate platform grievance draft."],
    },
    WorkflowStage.TIER1_DRAFT: {
        "description": "Draft and send a formal grievance email to the platform's grievance officer.",
        "prerequisites": ["Timeline verified, no unresolved critical conflicts."],
        "next_actions": ["Track platform response within SLA."],
    },
    WorkflowStage.PLATFORM_TRACKING: {
        "description": "Monitor the platform's response or non-response within the SLA window.",
        "prerequisites": ["Platform grievance email sent."],
        "next_actions": ["If unresolved, prepare for NCH escalation."],
    },
    WorkflowStage.TIER2_READINESS: {
        "description": "Prepare the case for National Consumer Helpline (NCH) escalation.",
        "prerequisites": [
            "Platform grievance sent.",
            "Platform SLA expired or response unsatisfactory.",
        ],
        "next_actions": ["Generate NCH docket."],
    },
    WorkflowStage.NCH_DOCKET: {
        "description": "Generate the NCH complaint filing summary and supporting documents.",
        "prerequisites": ["Tier 2 readiness confirmed."],
        "next_actions": ["If NCH unresolved, prepare for e-Jagriti."],
    },
    WorkflowStage.TIER3_CHECKLIST: {
        "description": "Pre-filing checklist for e-Jagriti Consumer Commission submission.",
        "prerequisites": [
            "NCH complaint filed.",
            "NCH process exhausted or response unsatisfactory.",
        ],
        "next_actions": ["Generate the final filing package."],
    },
    WorkflowStage.FINAL_FILING: {
        "description": "Generate the complete Consumer Commission filing package for e-Jagriti.",
        "prerequisites": ["Tier 3 pre-filing checklist complete."],
        "next_actions": ["Case filed with Consumer Commission."],
    },
}

# ── Prerequisites check helpers ────────────────────────────────────────────

def _has_evidence(case_id: str, db: Session) -> bool:
    """Return True if at least one evidence document exists."""
    return (
        db.query(EvidenceDocument)
        .filter(EvidenceDocument.case_id == case_id)
        .count()
        > 0
    )


def _has_platform_draft(case_id: str, db: Session) -> bool:
    """Return True if a platform_email draft has been generated."""
    from app.models import GeneratedDraft
    return (
        db.query(GeneratedDraft)
        .filter(
            GeneratedDraft.case_id == case_id,
            GeneratedDraft.draft_type == "platform_email",
        )
        .count()
        > 0
    )


def _has_nch_docket(case_id: str, db: Session) -> bool:
    """Return True if an NCH summary/docket has been generated."""
    from app.models import GeneratedDraft
    return (
        db.query(GeneratedDraft)
        .filter(
            GeneratedDraft.case_id == case_id,
            GeneratedDraft.draft_type == "nch_summary",
        )
        .count()
        > 0
    )


# Stage-specific prerequisites: returns (ok, reason)
_PREREQ_CHECKS: Dict[WorkflowStage, Any] = {}


def _check_prerequisites(
    case: Case, target_stage: WorkflowStage, db: Session
) -> tuple[bool, str]:
    """Return (can_advance, reason) for moving to target_stage."""

    # Must have all required slots filled before going past stage 3→4
    if target_stage == WorkflowStage.EVIDENCE_INGESTION:
        for slot in ("platform", "order_id", "issue_category", "amount",
                     "incident_date", "resolution_sought"):
            if not getattr(case, slot, None):
                return False, f"Missing required slot: {slot.replace('_', ' ')}"

    # Must have evidence before stage 4→5
    if target_stage == WorkflowStage.TIMELINE_RECONSTRUCTION:
        if not _has_evidence(case.id, db):
            return False, "At least one evidence document must be uploaded before building the timeline."

    # Must have platform draft before tracking (stage 7→8)
    if target_stage == WorkflowStage.PLATFORM_TRACKING:
        if not _has_platform_draft(case.id, db):
            return False, "Platform grievance email must be generated before tracking the response."

    # Must have platform response/draft before tier 2 (stage 8→9)
    if target_stage == WorkflowStage.TIER2_READINESS:
        if not _has_platform_draft(case.id, db):
            return False, "Platform grievance must have been sent before escalating to NCH."

    # Must have NCH docket before tier 3 (stage 10→11)
    if target_stage == WorkflowStage.TIER3_CHECKLIST:
        if not _has_nch_docket(case.id, db):
            return False, "NCH complaint docket must be generated before escalating to e-Jagriti."

    return True, "All prerequisites met."


# ── EscalationEngine ──────────────────────────────────────────────────────

class EscalationEngine:
    """Manages the 12-stage workflow state machine across 3 escalation tiers."""

    def _stage_index(self, stage_value: str) -> int:
        """Return the index in STAGE_ORDER for a stage value string."""
        for i, s in enumerate(STAGE_ORDER):
            if s.value == stage_value:
                return i
        raise ValueError(f"Unknown stage: {stage_value}")

    def _tier_for_stage(self, stage: WorkflowStage) -> EscalationTier:
        return TIER_MAP[stage]

    def _allowed_next(self, current_idx: int) -> List[str]:
        """Return allowed next stage values from current index."""
        if current_idx < len(STAGE_ORDER) - 1:
            return [STAGE_ORDER[current_idx + 1].value]
        return []

    # ── can_advance ────────────────────────────────────────────────────

    def can_advance(self, case_id: str, db: Session) -> Dict[str, Any]:
        """Check whether the case can advance to the next stage.

        Returns: {can_advance: bool, reason: str}
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return {"can_advance": False, "reason": "Case not found."}

        current_idx = self._stage_index(case.workflow_stage)
        if current_idx >= len(STAGE_ORDER) - 1:
            return {
                "can_advance": False,
                "reason": "Case is already at the final stage.",
            }

        next_stage = STAGE_ORDER[current_idx + 1]
        ok, reason = _check_prerequisites(case, next_stage, db)
        return {"can_advance": ok, "reason": reason}

    # ── advance_stage ──────────────────────────────────────────────────

    def advance_stage(self, case_id: str, db: Session) -> Dict[str, Any]:
        """Advance the case to the next workflow stage (if prerequisites met).

        Returns:
            {prev_stage, current_stage, prev_tier, current_tier,
             allowed_next, message}
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        current_idx = self._stage_index(case.workflow_stage)
        if current_idx >= len(STAGE_ORDER) - 1:
            return {
                "prev_stage": case.workflow_stage,
                "current_stage": case.workflow_stage,
                "prev_tier": case.escalation_tier,
                "current_tier": case.escalation_tier,
                "allowed_next": [],
                "message": "Case is already at the final stage.",
            }

        next_stage = STAGE_ORDER[current_idx + 1]
        ok, reason = _check_prerequisites(case, next_stage, db)
        if not ok:
            return {
                "prev_stage": case.workflow_stage,
                "current_stage": case.workflow_stage,
                "prev_tier": case.escalation_tier,
                "current_tier": case.escalation_tier,
                "allowed_next": [next_stage.value],
                "message": f"Cannot advance: {reason}",
            }

        prev_stage = case.workflow_stage
        prev_tier = case.escalation_tier
        new_tier = self._tier_for_stage(next_stage)

        # Update case
        case.workflow_stage = next_stage.value
        case.escalation_tier = new_tier.value

        # Log transition
        history = EscalationHistory(
            case_id=case.id,
            from_stage=prev_stage,
            to_stage=next_stage.value,
            from_tier=prev_tier,
            to_tier=new_tier.value,
            reason=f"Advanced from stage {current_idx + 1} to {current_idx + 2}.",
        )
        db.add(history)
        db.commit()
        db.refresh(case)

        new_idx = current_idx + 1
        return {
            "prev_stage": prev_stage,
            "current_stage": next_stage.value,
            "prev_tier": prev_tier,
            "current_tier": new_tier.value,
            "allowed_next": self._allowed_next(new_idx),
            "message": f"Advanced to {next_stage.value}.",
        }

    # ── set_stage ──────────────────────────────────────────────────────

    def set_stage(
        self, case_id: str, target_stage: str, db: Session
    ) -> Dict[str, Any]:
        """Force-set the case to a specific stage (with validation).

        Raises ValueError if the target stage is invalid.
        Returns the same dict shape as advance_stage.
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        # Validate target stage
        target_ws: Optional[WorkflowStage] = None
        for s in WorkflowStage:
            if s.value == target_stage:
                target_ws = s
                break
        if target_ws is None:
            raise ValueError(f"Invalid stage: {target_stage}")

        prev_stage = case.workflow_stage
        prev_tier = case.escalation_tier
        new_tier = self._tier_for_stage(target_ws)
        target_idx = self._stage_index(target_stage)

        case.workflow_stage = target_ws.value
        case.escalation_tier = new_tier.value

        history = EscalationHistory(
            case_id=case.id,
            from_stage=prev_stage,
            to_stage=target_ws.value,
            from_tier=prev_tier,
            to_tier=new_tier.value,
            reason=f"Stage manually set to {target_ws.value}.",
        )
        db.add(history)
        db.commit()
        db.refresh(case)

        return {
            "prev_stage": prev_stage,
            "current_stage": target_ws.value,
            "prev_tier": prev_tier,
            "current_tier": new_tier.value,
            "allowed_next": self._allowed_next(target_idx),
            "message": f"Stage set to {target_ws.value}.",
        }

    # ── get_stage_info ─────────────────────────────────────────────────

    def get_stage_info(self, stage: str) -> Dict[str, Any]:
        """Return metadata about a specific workflow stage.

        Returns: {description, tier, prerequisites, next_actions}
        """
        target_ws: Optional[WorkflowStage] = None
        for s in WorkflowStage:
            if s.value == stage:
                target_ws = s
                break
        if target_ws is None:
            raise ValueError(f"Unknown stage: {stage}")

        info = _STAGE_INFO[target_ws]
        tier = self._tier_for_stage(target_ws)
        return {
            "description": info["description"],
            "tier": tier.value,
            "prerequisites": info["prerequisites"],
            "next_actions": info["next_actions"],
        }
