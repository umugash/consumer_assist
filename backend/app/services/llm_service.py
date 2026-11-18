"""LLM Service — Real-time conversational routing, state management, and multimodal OCR.

Supports OpenAI (e.g. gpt-4o-mini) and Google Gemini (e.g. gemini-1.5-flash) with
structured JSON outputs, and includes an intelligent zero-latency local fallback
router to ensure zero downtime.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Case, DialogueTurn, EvidenceDocument, WorkflowStage
from app.services.nlp_extractor import (
    classify_complaint,
    extract_entities,
    normalize_date,
    resolve_platform,
    disambiguate_amount,
)

logger = logging.getLogger(__name__)

# Stage descriptions for intelligent context injection & query answering
STAGE_GUIDES: Dict[int, Dict[str, str]] = {
    1: {
        "name": "Intake & Greeting",
        "description": "Initial greeting and case creation.",
        "user_action": "Describe what went wrong with your order in plain English.",
    },
    2: {
        "name": "Issue Classification",
        "description": "Automated categorization of the dispute (e.g., Refund Delayed/Denied, Wrong/Missing Item, Damaged Goods).",
        "user_action": "Confirm or adjust the detected complaint category.",
    },
    3: {
        "name": "Slot Filling (DST)",
        "description": "Gathering critical case facts: platform name, order ID, disputed amount, incident date, and relief sought.",
        "user_action": "Provide missing transaction and order details.",
    },
    4: {
        "name": "Evidence Ingestion & OCR",
        "description": "Uploading invoices, delivery screenshots, and support chat proofs to extract fields and compute your Case Readiness Score.",
        "user_action": "Attach receipts/screenshots with the '+' button, or click Skip to move forward.",
    },
    5: {
        "name": "Timeline Reconstruction",
        "description": "Reconstructing an evidence-grounded, chronological timeline of all events to establish platform SLA breaches and legal delays.",
        "user_action": "Review the chronological timeline events and audit checks in the Timeline tab.",
    },
    6: {
        "name": "Conflict & Gap Verification",
        "description": "Cross-verifying user statements against OCR evidence to detect any date or amount discrepancies before filing.",
        "user_action": "Review identified discrepancies or confirm the facts are consistent.",
    },
    7: {
        "name": "Tier 1: Platform Grievance Routing & Draft",
        "description": "Synthesizing a statutory legal grievance notice citing Rule 4(5) of the Consumer Protection (E-Commerce) Rules 2020 addressed to the Grievance Officer.",
        "user_action": "Copy and email the generated legal notice to the platform's Grievance Officer.",
    },
    8: {
        "name": "Platform SLA/Response Tracking",
        "description": "Monitoring the statutory 48-hour acknowledgment and one-month redressal window (Rule 4(5)) for the platform's response.",
        "user_action": "Record whether the platform accepted, rejected, or ignored your notice.",
    },
    9: {
        "name": "Tier 2: NCH Readiness",
        "description": "Preparing your case for statutory escalation to the National Consumer Helpline (NCH - 1915 / consumerhelpline.gov.in).",
        "user_action": "Verify prerequisite compliance before escalating to Tier 2.",
    },
    10: {
        "name": "NCH Docket Generation",
        "description": "Generating a formal National Consumer Helpline complaint summary and evidence docket package.",
        "user_action": "Download the NCH docket and lodge your grievance on the NCH portal.",
    },
    11: {
        "name": "Tier 3: e-Jagriti Pre-Filing Checklist",
        "description": "Final legal-tech audit verifying limitation periods (Section 69, 2-year window), jurisdiction, and fee exemptions under the Consumer Protection Act 2019.",
        "user_action": "Review the statutory checklist before filing a formal consumer court case.",
    },
    12: {
        "name": "Final Consumer Commission Filing Package",
        "description": "Generating the comprehensive Section 35 Consumer Complaint petition, affidavit, and indexed annexures for e-Jagriti e-filing.",
        "user_action": "Download your petition package and upload it directly to the e-Jagriti portal.",
    },
}


def _get_api_keys() -> tuple[Optional[str], Optional[str]]:
    """Retrieve OpenAI and Gemini API keys from settings or environment."""
    openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    gemini_key = (
        settings.GEMINI_API_KEY
        or settings.GOOGLE_API_KEY
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    return (
        openai_key.strip() if openai_key and openai_key.strip() else None,
        gemini_key.strip() if gemini_key and gemini_key.strip() else None,
    )


# ── Core LLM Dialogue Handler ────────────────────────────────────────────────

def chat_with_llm(
    case: Case,
    user_message: str,
    db: Session,
) -> Dict[str, Any]:
    """Process a user message using real-time LLM routing or intelligent local fallback.

    Returns:
        {
            "bot_message": str,
            "extracted_slots": dict,
            "intent_action": "advance_stage" | "slot_fill" | "answer_query" | "waive_evidence" | "correct_category" | "general_chat",
            "provider_used": str
        }
    """
    openai_key, gemini_key = _get_api_keys()

    providers = []
    if gemini_key:
        providers.append(("gemini", _call_gemini_chat, gemini_key))
    if openai_key:
        providers.append(("openai", _call_openai_chat, openai_key))
    for name, fn, key in providers:
        try:
            res = _validate_llm_output(fn(case, user_message, db, key))
            if res:
                res["provider_used"] = name
                return res
            logger.warning(f"{name} returned an invalid/empty structured response; trying next provider.")
        except Exception as exc:
            try: db.rollback()
            except Exception: pass
            # Only the type is logged: exception text could echo request details.
            logger.warning(f"{name} chat routing failed ({type(exc).__name__}); trying next provider.")

    # High-precision Zero-Failure Local Fallback
    fallback_res = _local_fallback_router(case, user_message, db)
    fallback_res["provider_used"] = "local_rules_engine"
    return fallback_res


_REQUIRED_FOR_PROMPT = ("platform", "order_id", "issue_category", "amount", "incident_date", "resolution_sought")


def _missing_required(case: Case) -> List[str]:
    return [s for s in _REQUIRED_FOR_PROMPT if getattr(case, s, None) in (None, "")]


def _build_system_prompt(case: Case, db: Session) -> str:
    """Build structured context injection prompt for the LLM."""
    docs = (
        db.query(EvidenceDocument)
        .filter(EvidenceDocument.case_id == case.id)
        .all()
    )
    doc_summary = [
        f"- {d.filename} ({(d.extracted_fields or {}).get('document_type') or d.file_type or 'Uncategorized'})"
        for d in docs
    ]
    doc_str = "\n".join(doc_summary) if doc_summary else "No evidence documents uploaded yet."

    return f"""You are ConsumerAssist AI, an expert computational case-intelligence and legal-tech conversational agent for Indian e-commerce consumer grievance resolution (Amazon, Flipkart, Zepto, Blinkit, Swiggy Instamart).
You guide consumers across 12 workflow stages and 3 Escalation Tiers (Tier 1: Platform, Tier 2: NCH, Tier 3: e-Jagriti) grounded in the Consumer Protection Act 2019 and E-Commerce Rules 2020.

CURRENT CASE CONTEXT:
- Active Stage: {case.workflow_stage or '1. Intake & Greeting'}
- Platform: {case.platform or 'Not provided'}
- Order ID: {case.order_id or 'Not provided'}
- Disputed Amount: ₹{case.amount or 'Not provided'}
- Incident Date: {case.incident_date or 'Not provided'}
- Issue Category: {case.issue_category or 'Not provided'}
- Resolution / Relief Sought: {case.resolution_sought or 'Not provided'}
- Customer Support Contacted: {case.customer_support_contacted}
- Ingested Documents ({len(docs)}):
{doc_str}

- Today's date: {datetime.now().strftime('%Y-%m-%d (%A)')}
- Still missing (ask for ONE of these, conversationally, when not answering a question): {', '.join(_missing_required(case)) or 'none'}

SLOT EXTRACTION RULES (critical):
A. extracted_slots must contain ONLY values the user states or corrects in their LATEST message; use null for everything else. Never invent values, never repeat existing values.
B. If the user corrects an earlier value ("actually it was ₹2,100", "sorry, it was Flipkart"), return the new value.
C. platform = the e-commerce platform/app where the order was placed (Amazon, Flipkart, Zepto, Blinkit, Swiggy Instamart, Myntra, Meesho, ...). A brand mentioned as a product ("Amazon Pay gift card bought on Zepto", "Samsung phone") is NOT the platform.
D. amount = the money the consumer actually paid / is disputing. Face values, denominations, MRP printed on packaging or prices of other items are NOT the amount. If several amounts are ambiguous, set amount null and ask which one was paid.
E. incident_date in YYYY-MM-DD; resolve relative dates (yesterday, last Monday) using today's date and Indian DD/MM/YYYY ordering. If unsure, null and ask.
F. issue_category must be one of: Non-Delivery, Damaged/Defective Item, Wrong/Missing Item, Refund Delayed/Denied, Hidden Charges/Overbilling, Expired Food/Quick-Commerce Issue, Other. Being charged above the printed MRP, or extra/undisclosed fees, is Hidden Charges/Overbilling.
H. Never tell the user to look in a tab or panel; everything they need is given in the chat itself. If the user says they don't have a detail, accept it and move on.
G. Typos and informal Hinglish are normal; interpret intent generously.

BEHAVIORAL RULES:
1. Always be conversational, concise, and helpful (1-4 sentences). Never restart the workflow or re-ask for details already in CURRENT CASE CONTEXT.
1a. If the user asks you to repeat or asks about something said earlier, use the conversation history.
1b. Explain legal concepts only at a general level: Rule 4(5) of the Consumer Protection (E-Commerce) Rules 2020 requires the platform Grievance Officer to acknowledge a complaint within 48 hours and redress it within one month; NCH (1915 / consumerhelpline.gov.in) is pre-litigation mediation; e-Jagriti is the e-filing portal for Consumer Commissions (complaint under Section 35, limitation 2 years under Section 69 of the Consumer Protection Act 2019). Do not invent other provisions, deadlines or document requirements; say you are not certain if asked something outside this.
1c. Questions ("why do you need my invoice?", "is a bank statement compulsory?", "what happens next?") must use intent_action "answer_query" and never advance the stage. An invoice proves the transaction, amount and seller; bank/UPI proof is waived for Cash on Delivery; the user may skip any document and continue, with a lower readiness score.
2. NEVER copy-paste long, repetitive evidence checklists or boilerplate forms into the chat.
3. If the user asks a question (e.g. "what to do in stage 5", "how does NCH work?", "what is the limitation period?"):
   - Set intent_action: "answer_query"
   - Answer the question directly and conversationally in 1-2 sentences. If asking about a stage, explain what that stage does and mention they can advance when ready.
4. Only if the user explicitly asks to move on (e.g. "proceed", "skip", "next stage", "done uploading"):
   - Set intent_action: "advance_stage"
5. If the user mentions payment method is Cash on Delivery ("paid as cod", "cash"):
   - Set intent_action: "waive_evidence"
   - extracted_slots: {{"payment_mode": "COD"}}
6. If the user corrects a document type (e.g. "no that was the invoice", "that is the bill"):
   - Set intent_action: "correct_category"
   - extracted_slots: {{"document_type": "Order confirmation / invoice"}}
7. If the user specifies any desired resolution, remedy, or outcome (e.g. "refund", "replacement", "compensation", "apology", or open-ended intents like "nothing just inform them", "just inform", "give feedback", "take action"):
   - Set intent_action: "slot_fill"
   - Summarize this in "resolution_sought" (e.g., "Inform the platform / No monetary claim", "Full refund", "Product replacement"). NEVER ignore or fail to extract open-ended non-monetary relief preferences!
8. If the user supplies case details (order ID, date, amount, platform):
   - Set intent_action: "slot_fill"
   - Fill the extracted_slots object.

OUTPUT REQUIREMENT:
You must respond with ONLY a valid JSON object matching this exact schema:
{{
  "bot_message": "Concise conversational response to the user",
  "extracted_slots": {{
    "platform": "Zepto | Amazon | ... or null",
    "order_id": "string or null",
    "amount": number or null,
    "incident_date": "YYYY-MM-DD or null",
    "customer_support_contacted": boolean or null,
    "issue_category": "string or null",
    "resolution_sought": "string summarizing desired remedy: e.g. 'Full refund', 'Product replacement', 'Inform the platform / No monetary claim', 'Compensation', or verbatim summary. Do NOT leave null if user answered what outcome they want!",
    "payment_mode": "string or null",
    "document_type": "string or null"
  }},
  "intent_action": "advance_stage" | "slot_fill" | "answer_query" | "waive_evidence" | "correct_category" | "general_chat"
}}
"""


def _normalize_extracted_slots(slots: Any) -> Dict[str, Any]:
    """Ensure slot keys are canonical (e.g. map relief_sought -> resolution_sought)."""
    if not isinstance(slots, dict):
        return {}
    res = dict(slots)
    for alias in ("relief_sought", "remedy", "relief", "resolution", "remedy_sought", "relief_remedy"):
        if alias in res:
            val = res.pop(alias)
            if val and not res.get("resolution_sought"):
                res["resolution_sought"] = val
    return res



# ── OpenAI Provider ─────────────────────────────────────────────────────────

def _call_openai_chat(
    case: Case,
    user_message: str,
    db: Session,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    import openai
    client = openai.OpenAI(api_key=api_key, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=0)

    recent_turns = _recent_history(case, db)

    messages = [{"role": "system", "content": _build_system_prompt(case, db)}]
    for turn in recent_turns:
        messages.append({
            "role": "assistant" if turn.role == "assistant" else "user",
            "content": turn.message,
        })
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=settings.LLM_TIMEOUT_SECONDS,
    )
    return _parse_json_text(response.choices[0].message.content or "")


# ── Google Gemini Provider ──────────────────────────────────────────────────

def _recent_history(case: Case, db: Session, limit: int = 10) -> List[DialogueTurn]:
    turns = (
        db.query(DialogueTurn)
        .filter(DialogueTurn.case_id == case.id)
        .order_by(DialogueTurn.turn_number.desc())
        .limit(limit)
        .all()
    )
    turns.reverse()
    return turns


def _call_gemini_chat(
    case: Case,
    user_message: str,
    db: Session,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    """Call Gemini over REST. The google.generativeai SDK is deprecated and the
    1.5 models it targeted are retired. The key goes in a header, never the URL."""
    import urllib.request
    import urllib.error

    contents: List[Dict[str, Any]] = []
    for t in _recent_history(case, db):
        role = "model" if t.role == "assistant" else "user"
        if contents and contents[-1]["role"] == role:  # Gemini wants alternating roles
            contents[-1]["parts"][0]["text"] += "\n" + t.message
        else:
            contents.append({"role": role, "parts": [{"text": t.message}]})
    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "(conversation start)"}]})
    if contents and contents[-1]["role"] == "user":
        contents.append({"role": "model", "parts": [{"text": "(noted)"}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": _build_system_prompt(case, db)}]},
        "contents": contents,
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
    }).encode("utf-8")

    models = [settings.GEMINI_MODEL] + [m for m in ("gemini-flash-lite-latest", "gemini-flash-latest") if m != settings.GEMINI_MODEL]
    last_exc: Optional[Exception] = None
    for model in models:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=settings.LLM_TIMEOUT_SECONDS) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            logger.warning(f"Gemini model {model} returned HTTP {exc.code}")
            if exc.code in (404, 429, 500, 503):  # retired / quota / overloaded -> next model
                continue
            raise
        candidates = res_data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or [{}]
        return _parse_json_text(parts[0].get("text", ""))
    if last_exc:
        raise last_exc
    return None


def _parse_json_text(text: str) -> Optional[Dict[str, Any]]:
    cleaned = (text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


_VALID_INTENTS = {"advance_stage", "slot_fill", "answer_query", "waive_evidence", "correct_category", "general_chat"}
_NULLISH = {"null", "none", "n/a", "unknown", "not provided"}


def _validate_llm_output(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Reject malformed LLM output before it can touch case state."""
    if not isinstance(data, dict):
        return None
    msg = data.get("bot_message")
    intent = data.get("intent_action")
    if not isinstance(msg, str) or not msg.strip() or intent not in _VALID_INTENTS:
        return None
    clean: Dict[str, Any] = {}
    for k, v in _normalize_extracted_slots(data.get("extracted_slots") or {}).items():
        if v is None or (isinstance(v, str) and v.strip().lower() in _NULLISH | {""}):
            continue
        if k == "amount":
            try:
                v = float(str(v).replace(",", "").replace("₹", "").replace("Rs", "").strip())
            except ValueError:
                continue
            if v <= 0:
                continue
        elif k == "incident_date":
            v = normalize_date(str(v))
            if not v:
                continue
        elif k == "customer_support_contacted":
            if not isinstance(v, bool):
                continue
        elif k in ("platform", "order_id", "issue_category", "resolution_sought", "payment_mode", "document_type"):
            v = str(v).strip()[:200]
        else:
            continue
        clean[k] = v
    return {"bot_message": msg.strip(), "extracted_slots": clean, "intent_action": intent}


def is_cod_message(text_lower: str) -> bool:
    """Word-boundary COD detection ('promo code' must not waive evidence)."""
    return bool(re.search(r"\bcod\b|cash on delivery|\bpaid (?:by|in|as) cash\b|\bcash payment\b", text_lower))


# ── Intelligent Zero-Failure Fallback Router ────────────────────────────────

def _local_fallback_router(
    case: Case,
    user_message: str,
    db: Session,
) -> Dict[str, Any]:
    """Robust pattern-based NLP router that mimics the LLM's structured output."""
    clean_lower = user_message.strip().lower()
    extracted_slots: Dict[str, Any] = {}

    # 1. Check for Advance / Skip / Proceed Intent
    skip_phrases = ["skip", "done", "no more", "proceed", "next stage", "advance", "continue", "move to stage", "go to stage"]
    if any(p in clean_lower for p in skip_phrases) and not clean_lower.startswith("what"):
        return {
            "bot_message": "Proceeding to the next workflow stage.",
            "extracted_slots": {},
            "intent_action": "advance_stage",
        }

    # 2. Check for Questions about Stages (e.g., "ok what to do in stage 5", "what is stage 5")
    stage_match = re.search(r"(?:stage|step)\s*(\d+)", clean_lower)
    is_stage_query = ("what" in clean_lower or "how" in clean_lower or "explain" in clean_lower or "tell me" in clean_lower) and stage_match

    if is_stage_query or ("timeline" in clean_lower and "what" in clean_lower):
        stage_num = int(stage_match.group(1)) if stage_match else 5
        stage_data = STAGE_GUIDES.get(stage_num, STAGE_GUIDES[5])
        
        reply = (
            f"In **Stage {stage_num}: {stage_data['name']}**, {stage_data['description']} "
            f"When you are ready, click **[Advance Stage]** or type **'proceed'** to continue."
        )
        return {
            "bot_message": reply,
            "extracted_slots": {},
            "intent_action": "answer_query",
        }

    # 3. Check for Cash on Delivery / COD
    if is_cod_message(clean_lower):
        return {
            "bot_message": "Understood! Since this order was paid via Cash on Delivery (COD), the bank/UPI statement requirement is waived.",
            "extracted_slots": {"payment_mode": "COD"},
            "intent_action": "waive_evidence",
        }

    # 4. Check for Document Categorization Correction
    correction_indicators = ["no that", "that was", "that is", "that's", "this was", "this is", "correct it to"]
    if any(ci in clean_lower for ci in correction_indicators) or (
        any(kw in clean_lower for kw in ["invoice", "bill", "receipt", "support chat", "bank statement", "payment proof"])
        and ("no" in clean_lower or "was" in clean_lower or "is" in clean_lower)
    ):
        if any(k in clean_lower for k in ["invoice", "bill", "receipt", "summary"]):
            new_cat = "Order confirmation / invoice"
        elif any(k in clean_lower for k in ["support", "chat", "agent"]):
            new_cat = "Chat with customer support"
        elif any(k in clean_lower for k in ["refund", "rejection", "status"]):
            new_cat = "Refund request/status screenshot"
        elif any(k in clean_lower for k in ["payment", "bank", "upi", "statement"]):
            new_cat = "Payment proof (bank/UPI statement)"
        else:
            new_cat = "Photo of received item vs ordered item"

        return {
            "bot_message": f"Got it — updating document categorization to **{new_cat}**.",
            "extracted_slots": {"document_type": new_cat},
            "intent_action": "correct_category",
        }

    # 5. Question Answering on Legal / Statutory Framework
    if any(q in clean_lower for q in ["nch", "national consumer helpline"]):
        return {
            "bot_message": "The National Consumer Helpline (NCH - 1915) is the government's official alternative dispute resolution pre-litigation portal operated by the Department of Consumer Affairs.",
            "extracted_slots": {},
            "intent_action": "answer_query",
        }
    if any(q in clean_lower for q in ["ejagriti", "e-jagriti", "commission", "court"]):
        return {
            "bot_message": "e-Jagriti is the official digital portal for filing consumer complaints online before District, State, and National Consumer Dispute Redressal Commissions under Section 35 of the CPA 2019.",
            "extracted_slots": {},
            "intent_action": "answer_query",
        }

    # 5.5 Check for Relief / Resolution Sought (e.g. "nothing just inform them", "just inform", "refund", "replacement")
    last_assistant_turn = None
    try:
        last_assistant_turn = (
            db.query(DialogueTurn)
            .filter(DialogueTurn.case_id == case.id, DialogueTurn.role == "assistant")
            .order_by(DialogueTurn.turn_number.desc())
            .first()
        )
    except Exception:
        try: db.rollback()
        except Exception: pass

    is_answering_resolution = False
    if last_assistant_turn and last_assistant_turn.message:
        msg_l = last_assistant_turn.message.lower()
        if "resolution are you seeking" in msg_l or "remedy" in msg_l or "refund, replacement" in msg_l:
            is_answering_resolution = True

    resolution_phrases = ["inform", "feedback", "nothing", "just inform", "apology", "replace", "refund", "compensation", "no remedy", "fix", "action"]
    if is_answering_resolution or any(rp in clean_lower for rp in resolution_phrases):
        if any(w in clean_lower for w in ["inform", "nothing", "feedback", "aware", "notice"]):
            res_val = "Inform the platform / No monetary claim"
        elif "refund" in clean_lower:
            res_val = "Full refund"
        elif "replace" in clean_lower or "exchange" in clean_lower:
            res_val = "Product replacement"
        elif "compensation" in clean_lower or "damages" in clean_lower:
            res_val = "Compensation for inconvenience/loss"
        else:
            res_val = user_message.strip()[:100]

        extracted_slots["resolution_sought"] = res_val
        return {
            "bot_message": f"Got it — I have recorded your preferred resolution: **{res_val}**.",
            "extracted_slots": extracted_slots,
            "intent_action": "slot_fill",
        }

    # 6. Slot Extraction & Entity Disambiguation
    entities = extract_entities(user_message)
    intent_data = classify_complaint(user_message)

    platform_cand = [e["value"] for e in entities if e.get("type") == "PLATFORM"]
    resolved_plat = resolve_platform(user_message, platform_cand)
    if resolved_plat:
        extracted_slots["platform"] = resolved_plat

    resolved_amt = disambiguate_amount(user_message, entities)
    if resolved_amt is not None:
        extracted_slots["amount"] = resolved_amt

    order_ids = [e["value"] for e in entities if e.get("type") == "ORDER_ID"]
    if order_ids:
        extracted_slots["order_id"] = order_ids[0]
    else:
        # Regex fallback for order id
        oid_m = re.search(r"(?:order\s*(?:id|#|no\.?)\s*[:=\-]?\s*)([A-Za-z0-9_\-]+)", user_message, re.IGNORECASE)
        if oid_m:
            extracted_slots["order_id"] = oid_m.group(1).strip()

    dates = [e.get("normalized_value") or e.get("value") for e in entities if e.get("type") == "DATE"]
    if dates:
        extracted_slots["incident_date"] = normalize_date(dates[0]) or dates[0]

    category = intent_data.get("intent") or intent_data.get("category")
    if category and category != "unknown":
        extracted_slots["issue_category"] = category

    if extracted_slots:
        details = ", ".join(f"{k}: **{v}**" for k, v in extracted_slots.items())
        return {
            "bot_message": f"Understood, I have updated your case details with: {details}.",
            "extracted_slots": extracted_slots,
            "intent_action": "slot_fill",
        }

    return {
        "bot_message": f"I have noted your message: \"{user_message}\". How can I assist you with this stage?",
        "extracted_slots": {},
        "intent_action": "general_chat",
    }


# ── Multimodal Document Analysis with Vision ────────────────────────────────

def analyze_document_with_vision(
    file_path: str,
    mime_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Inspect an invoice or screenshot with Gemini 1.5 Flash or GPT-4o-mini vision."""
    openai_key, gemini_key = _get_api_keys()

    if not gemini_key:
        return None
    import base64
    import urllib.request
    import urllib.error

    prompt = """Analyze this consumer grievance evidence document (receipt, invoice, chat log, or delivery status).
Transcribe only what is visible; use null for anything not present. Never guess values.
A product photo or packaging/MRP label is NOT an invoice: classify it as a product photo and set total_amount null (put the printed MRP in items[].mrp).
Return a strict JSON object:
{
  "document_type": "Order confirmation / invoice" | "Refund request/status screenshot" | "Payment proof (bank/UPI statement)" | "Photo of received item vs ordered item" | "Photo of damaged/defective product" | "Chat with customer support" | "Delivery status screenshot",
  "vendor": "string or null",
  "order_id": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "total_amount": number or null,
  "payment_mode": "string or null",
  "items": [{"name": "string", "quantity": 1, "mrp": 0.0, "unit_price": 0.0, "total": 0.0}],
  "ocr_text": "verbatim key text from the document"
}"""
    path_l = file_path.lower()
    mtype = mime_type or (
        "application/pdf" if path_l.endswith(".pdf")
        else "image/png" if path_l.endswith(".png")
        else "image/webp" if path_l.endswith(".webp")
        else "image/jpeg"
    )
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    payload = json.dumps({
        "contents": [{"role": "user", "parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mtype, "data": b64}},
        ]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
    }).encode("utf-8")
    for model in dict.fromkeys([settings.GEMINI_MODEL, "gemini-flash-lite-latest", "gemini-flash-latest"]):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": gemini_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                res = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning(f"Gemini vision model {model} returned HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Gemini vision failed ({type(exc).__name__})")
            return None
        parts = ((res.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
        data = _parse_json_text(parts[0].get("text", ""))
        if data:
            if data.get("invoice_date"):
                data["invoice_date"] = normalize_date(str(data["invoice_date"])) or None
            return data
        return None
    return None

