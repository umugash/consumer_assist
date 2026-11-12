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
        "description": "Synthesizing a statutory legal grievance notice citing Rule 5(3)(b) Consumer Protection (E-Commerce) Rules 2020 addressed to the Grievance Officer.",
        "user_action": "Copy and email the generated legal notice to the platform's Grievance Officer.",
    },
    8: {
        "name": "Platform SLA/Response Tracking",
        "description": "Monitoring the statutory 48-hour acknowledgment and 30-day resolution window for the platform's response.",
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

    # If keys exist, attempt real LLM API call first
    if openai_key:
        try:
            res = _call_openai_chat(case, user_message, db, openai_key)
            if res:
                res["provider_used"] = "openai"
                return res
        except Exception as exc:
            try: db.rollback()
            except Exception: pass
            logger.warning(f"OpenAI chat routing failed ({exc}), falling back to local engine.")

    if gemini_key:
        try:
            res = _call_gemini_chat(case, user_message, db, gemini_key)
            if res:
                res["provider_used"] = "gemini"
                return res
        except Exception as exc:
            try: db.rollback()
            except Exception: pass
            logger.warning(f"Gemini chat routing failed ({exc}), falling back to local engine.")

    # High-precision Zero-Failure Local Fallback
    fallback_res = _local_fallback_router(case, user_message, db)
    fallback_res["provider_used"] = "local_rules_engine"
    return fallback_res


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

BEHAVIORAL RULES:
1. Always be conversational, concise, and helpful (1-3 sentences maximum).
2. NEVER copy-paste long, repetitive evidence checklists or boilerplate forms into the chat.
3. If the user asks a question (e.g. "what to do in stage 5", "how does NCH work?", "what is the limitation period?"):
   - Set intent_action: "answer_query"
   - Answer the question directly and conversationally in 1-2 sentences. If asking about a stage, explain what that stage does and mention they can advance when ready.
4. If the user wants to advance (e.g. "proceed", "skip", "advance", "next stage", "done"):
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
    client = openai.OpenAI(api_key=api_key, timeout=5.0, max_retries=0)

    recent_turns = (
        db.query(DialogueTurn)
        .filter(DialogueTurn.case_id == case.id)
        .order_by(DialogueTurn.turn_number.desc())
        .limit(6)
        .all()
    )
    recent_turns.reverse()

    messages = [{"role": "system", "content": _build_system_prompt(case, db)}]
    for turn in recent_turns:
        messages.append({
            "role": "assistant" if turn.role == "assistant" else "user",
            "content": turn.message,
        })
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=settings.LLM_MODEL or "gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=5.0,
    )
    raw = response.choices[0].message.content
    if raw:
        data = json.loads(raw)
        return {
            "bot_message": data.get("bot_message", ""),
            "extracted_slots": _normalize_extracted_slots(data.get("extracted_slots", {})),
            "intent_action": data.get("intent_action", "general_chat"),
        }
    return None


# ── Google Gemini Provider ──────────────────────────────────────────────────

def _call_gemini_chat(
    case: Case,
    user_message: str,
    db: Session,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name="gemini-flash-latest",
        system_instruction=_build_system_prompt(case, db),
        generation_config={"response_mime_type": "application/json", "temperature": 0.2},
    )

    recent_turns = (
        db.query(DialogueTurn)
        .filter(DialogueTurn.case_id == case.id)
        .order_by(DialogueTurn.turn_number.desc())
        .limit(6)
        .all()
    )
    recent_turns.reverse()

    history = []
    for turn in recent_turns:
        history.append({
            "role": "model" if turn.role == "assistant" else "user",
            "parts": [turn.message],
        })

    chat = model.start_chat(history=history)
    response = chat.send_message(user_message, request_options={"timeout": 6.0})


    if response and response.text:
        data = json.loads(response.text)
        return {
            "bot_message": data.get("bot_message", ""),
            "extracted_slots": _normalize_extracted_slots(data.get("extracted_slots", {})),
            "intent_action": data.get("intent_action", "general_chat"),
        }
    return None



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
    cod_phrases = ["cod", "cash on delivery", "paid as cod", "paid by cash", "cash payment", "paid in cash"]
    if any(cp in clean_lower for cp in cod_phrases):
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

    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-flash-latest")

            with open(file_path, "rb") as f:
                image_bytes = f.read()

            prompt = """Analyze this consumer grievance evidence document (receipt, invoice, chat log, or delivery status).
Return a strict JSON object:
{
  "document_type": "Order confirmation / invoice" | "Refund request/status screenshot" | "Payment proof (bank/UPI statement)" | "Photo of received item vs ordered item" | "Chat with customer support",
  "vendor": "string or null",
  "order_id": "string or null",
  "total_amount": float or null,
  "date": "YYYY-MM-DD or null",
  "items": [{"name": "string", "quantity": 1, "unit_price": 0.0, "total": 0.0}],
  "ocr_text": "text content summary",
  "status": "success"
}
"""
            mtype = mime_type or ("image/jpeg" if file_path.lower().endswith((".jpg", ".jpeg")) else "image/png")
            response = model.generate_content([
                prompt,
                {"mime_type": mtype, "data": image_bytes},
            ])
            if response and response.text:
                cleaned_text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
                return json.loads(cleaned_text)
        except Exception as exc:
            logger.warning(f"Gemini vision analysis failed: {exc}")

    return None

