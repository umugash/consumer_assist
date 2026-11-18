"""Chat-driven escalation flow: offline capture, Tier 1 → NCH → e-Jagriti, resolution."""

from app.models import Case
import app.services.llm_service as llm
from app.services.dialogue_manager import DialogueManager, is_resolved_reply, _looks_like_question


def _case(db):
    c = Case(status="active", workflow_stage="1. Intake & Greeting", escalation_tier="Tier 1: Platform Escalation")
    db.add(c); db.commit()
    return c


def test_resolution_reply_detection():
    assert is_resolved_reply("they refunded the extra amount and apologised")
    assert is_resolved_reply("refund credited, issue resolved")
    assert not is_resolved_reply("no refund yet")
    assert not is_resolved_reply("they rejected it")
    assert not _looks_like_question("product shows 500 as mrp")
    assert _looks_like_question("why do you need my invoice")


def test_offline_flow_letter_nch_ejagriti(db_session, monkeypatch):
    monkeypatch.setattr(llm, "_get_api_keys", lambda: (None, None))  # Gemini/OpenAI outage
    dm, c = DialogueManager(), _case(db_session)
    dm.process_message(c, "I ordered groceries worth ₹523 from Zepto (ZPT-20261107-33254) and was charged above printed MRP, product shows ₹500 as MRP", db_session)
    assert (c.platform, c.amount, c.order_id) == ("Zepto", 523.0, "ZPT-20261107-33254")

    r = dm.process_message(c, "skip", db_session)          # missing details skipped -> evidence stage
    assert c.workflow_stage.startswith("4.")
    r = dm.process_message(c, "proceed", db_session)       # letter shown in chat, waiting for platform
    assert c.workflow_stage.startswith("8.") and "grievance@zeptonow.com" in r["assistant_message"]
    assert "```" in r["assistant_message"]
    r = dm.process_message(c, "no response after 4 days", db_session)
    assert c.workflow_stage.startswith("10.") and "consumerhelpline.gov.in" in r["assistant_message"]
    r = dm.process_message(c, "NCH could not resolve it", db_session)
    assert c.workflow_stage.startswith("12.") and "e-jagriti.gov.in" in r["assistant_message"]
    assert c.status == "active"


def test_platform_resolution_closes_case(db_session, monkeypatch):
    monkeypatch.setattr(llm, "_get_api_keys", lambda: (None, None))
    dm, c = DialogueManager(), _case(db_session)
    dm.process_message(c, "Flipkart charged ₹899 for ₹799 MRP shampoo, order OD445566778899", db_session)
    dm.process_message(c, "skip", db_session)
    dm.process_message(c, "proceed", db_session)
    dm.process_message(c, "they refunded the extra amount and apologised", db_session)
    assert c.status == "resolved"
