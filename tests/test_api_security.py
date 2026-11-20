"""API-level auth/isolation, upload validation and LLM output validation tests."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app import auth
from app.models import Case
import app.services.llm_service as llm

USERS = {"token-a": {"id": "user-a", "email": "a@test"}, "token-b": {"id": "user-b", "email": "b@test"}}


def fake_user(authorization: str = auth.Header(default="")):
    tok = authorization.replace("Bearer ", "")
    if tok not in USERS:
        raise HTTPException(status_code=401, detail="Sign in required")
    return USERS[tok]


@pytest.fixture()
def client(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[auth.current_user] = fake_user
    monkeypatch.setattr(llm, "_get_api_keys", lambda: (None, None))  # offline: local rules engine
    with TestClient(app) as c:
        db = Session()
        db.add(Case(id="case-a", user_id="user-a", status="active", workflow_stage="1. Intake & Greeting",
                    escalation_tier="Tier 1: Platform Grievance"))
        db.commit(); db.close()
        yield c
    app.dependency_overrides.clear()


A = {"Authorization": "Bearer token-a"}
B = {"Authorization": "Bearer token-b"}


def test_unauthenticated_requests_rejected(client):
    assert client.get("/api/cases/").status_code == 401
    assert client.get("/api/cases/case-a").status_code == 401
    assert client.post("/api/chat/send", json={"message": "hi"}).status_code == 401


def test_users_only_see_their_own_cases(client):
    assert [c["id"] for c in client.get("/api/cases/", headers=A).json()] == ["case-a"]
    assert client.get("/api/cases/", headers=B).json() == []
    for path in ("/api/cases/case-a", "/api/cases/case-a/timeline", "/api/cases/case-a/drafts",
                 "/api/chat/history/case-a"):
        assert client.get(path, headers=B).status_code == 404, path
    assert client.delete("/api/cases/case-a", headers=B).status_code == 404
    r = client.post("/api/chat/send", json={"case_id": "case-a", "message": "hi"}, headers=B)
    assert r.status_code == 404


def test_new_case_owned_by_token_user_not_body(client):
    r = client.post("/api/chat/send", json={"message": "Zepto order", "user_id": "user-a"}, headers=B)
    assert r.status_code == 200
    ids = [c["id"] for c in client.get("/api/cases/", headers=B).json()]
    assert r.json()["case_id"] in ids
    assert r.json()["case_id"] not in [c["id"] for c in client.get("/api/cases/", headers=A).json()]


def test_upload_validation(client):
    bad = client.post("/api/documents/upload/case-a", headers=A, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 415
    big = client.post("/api/documents/upload/case-a", headers=A,
                      files={"file": ("x.png", b"0" * (10 * 1024 * 1024 + 1), "image/png")})
    assert big.status_code == 413
    other = client.post("/api/documents/upload/case-a", headers=B, files={"file": ("x.png", b"123", "image/png")})
    assert other.status_code == 404


def test_llm_output_validation_rejects_malformed():
    assert llm._validate_llm_output(None) is None
    assert llm._validate_llm_output({"bot_message": "", "intent_action": "slot_fill"}) is None
    assert llm._validate_llm_output({"bot_message": "x", "intent_action": "delete_everything"}) is None
    assert llm._parse_json_text("not json {") is None
    out = llm._validate_llm_output({"bot_message": "ok", "intent_action": "slot_fill",
                                    "extracted_slots": {"amount": "₹1,995", "incident_date": "garbage",
                                                        "platform": "null", "evil": "x"}})
    assert out["extracted_slots"] == {"amount": 1995.0}


def test_cod_detection_word_boundary():
    assert llm.is_cod_message("i paid by cash on delivery")
    assert llm.is_cod_message("it was cod")
    assert not llm.is_cod_message("i used a promo code")


def test_provider_failure_falls_back_to_local(monkeypatch):
    import urllib.error
    from app.services.dialogue_manager import DialogueManager
    eng = create_engine("sqlite://"); Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    case = Case(status="active", workflow_stage="1. Intake & Greeting", escalation_tier="Tier 1: Platform Grievance")
    db.add(case); db.commit()
    monkeypatch.setattr(llm, "_get_api_keys", lambda: (None, "fake"))
    for err in (urllib.error.HTTPError("u", 429, "quota", {}, None), TimeoutError(), ValueError("bad json")):
        def boom(*a, _e=err, **k):
            raise _e
        monkeypatch.setattr(llm, "_call_gemini_chat", boom)
        res = llm.chat_with_llm(case, "My Flipkart order of Rs 500 never arrived", db)
        assert res["provider_used"] == "local_rules_engine"
    # an explicit question never advances the stage, even offline
    DialogueManager().process_message(case, "why do you need my invoice?", db)
    assert case.workflow_stage == "1. Intake & Greeting"
    # premature advance is blocked while required slots are missing
    DialogueManager().process_message(case, "proceed", db)
    assert case.workflow_stage in ("1. Intake & Greeting", "2. Issue Classification", "3. Slot Filling")


def test_empty_or_oversized_message_rejected(client):
    for msg in ("", "   ", "x" * 4001):
        assert client.post("/api/chat/send", json={"message": msg}, headers=A).status_code == 422
