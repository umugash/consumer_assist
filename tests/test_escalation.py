"""Tests for the 12-Stage & 3-Tier Escalation State Machine."""

import pytest
from app.models import Case, WorkflowStage, EscalationTier, CaseStatus
from app.services.escalation_engine import EscalationEngine


def test_escalation_flow(db_session, sample_case):
    """Test standard forward progression through the guided workflow stages."""
    engine = EscalationEngine()
    
    # Initial stage should be Intake
    assert sample_case.workflow_stage == WorkflowStage.INTAKE.value
    assert sample_case.escalation_tier == EscalationTier.TIER_1_PLATFORM.value

    # Advance stage
    res = engine.advance_stage(sample_case.id, db_session)
    assert res["current_stage"] == WorkflowStage.CLASSIFICATION.value

    # Advance again
    res = engine.advance_stage(sample_case.id, db_session)
    assert res["current_stage"] == WorkflowStage.SLOT_FILLING.value


def test_tier_transitions(db_session, sample_case):
    """Verify tier transition logic when moving to Tier 2 and Tier 3."""
    engine = EscalationEngine()

    # Move to NCH Readiness (Stage 9)
    res = engine.set_stage(sample_case.id, WorkflowStage.TIER2_READINESS.value, db_session)
    assert res["current_tier"] == EscalationTier.TIER_2_NCH.value

    # Move to e-Jagriti Pre-Filing (Stage 11)
    res = engine.set_stage(sample_case.id, WorkflowStage.TIER3_CHECKLIST.value, db_session)
    assert res["current_tier"] == EscalationTier.TIER_3_EJAGRITI.value

