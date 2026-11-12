"""Pytest configuration and shared fixtures for ConsumerAssist test suite."""

import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend directory to sys.path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.database import Base
from app.models import Case, WorkflowStage, EscalationTier, CaseStatus


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite database for testing."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture(scope="function")
def db_session(engine):
    """Yield a transactional database session."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_case(db_session):
    """Create a sample active case for testing."""
    case = Case(
        status=CaseStatus.ACTIVE.value,
        workflow_stage=WorkflowStage.INTAKE.value,
        escalation_tier=EscalationTier.TIER_1_PLATFORM.value,
        platform="Amazon",
        order_id="402-8834521-7789234",
        issue_category="Non-Delivery",
        amount=2499.0,
        incident_date="2026-10-25",
        customer_support_contacted=True,
        resolution_sought="Full refund",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case

