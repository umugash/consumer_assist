"""Tests for Dialogue State Tracking and conversational slot-filling."""

import pytest
from app.models import Case, WorkflowStage, EscalationTier, CaseStatus
from app.services.dialogue_manager import DialogueManager


def test_dialogue_slot_filling(db_session):
    """Test slot-filling from a natural user message on a fresh case."""
    from app.models import Case, CaseStatus, WorkflowStage, EscalationTier
    fresh_case = Case(
        status=CaseStatus.ACTIVE.value,
        workflow_stage=WorkflowStage.INTAKE.value,
        escalation_tier=EscalationTier.TIER_1_PLATFORM.value,
    )
    db_session.add(fresh_case)
    db_session.commit()
    db_session.refresh(fresh_case)

    dm = DialogueManager()
    msg = "I ordered on Flipkart for Rs. 15999, order OD432876512349876. The product arrived broken."
    res = dm.process_message(fresh_case, msg, db_session)

    # Check updated slots
    assert fresh_case.platform == "Flipkart"
    assert fresh_case.amount == 15999.0
    assert fresh_case.order_id == "OD432876512349876"
    assert fresh_case.issue_category is not None
    assert "assistant_message" in res
