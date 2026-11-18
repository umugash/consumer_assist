"""Dialogue state tracking and slot-filling engine for ConsumerAssist."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import (
    Case, DialogueTurn, ExtractedEntity, EvidenceDocument,
    IssueCategory, WorkflowStage,
)
from app.services.nlp_extractor import (
    classify_complaint,
    extract_entities,
    normalize_date,
    resolve_platform,
    disambiguate_amount,
)
from app.services.llm_service import chat_with_llm, is_cod_message

_ADVANCE_RE = re.compile(r"\b(skip|proceed|next stage|advance stage|move on)\b")
_CORRECTION_RE = re.compile(r"\b(actually|sorry|correction|correct(?:ed)? (?:it|amount|date)|not .* but|instead|changed?|wrong(?:ly)?)\b")
_EARLY_STAGES = (WorkflowStage.INTAKE.value, WorkflowStage.CLASSIFICATION.value, WorkflowStage.SLOT_FILLING.value)

logger = logging.getLogger(__name__)

# ── Slot definitions ───────────────────────────────────────────────────────

SLOT_NAMES: List[str] = [
    "platform",
    "order_id",
    "issue_category",
    "amount",
    "incident_date",
    "customer_support_contacted",
    "evidence_uploaded",
    "resolution_sought",
]

# Slots that *must* be filled before leaving the slot-filling stage.
REQUIRED_SLOTS: List[str] = [
    "platform",
    "order_id",
    "issue_category",
    "amount",
    "incident_date",
    "resolution_sought",
]

# Human-readable prompts for each missing slot.
SLOT_QUESTIONS: Dict[str, str] = {
    "platform": "Which e-commerce platform was this order placed on (e.g. Amazon, Flipkart, Swiggy)?",
    "order_id": "Could you share the order ID or reference number?",
    "issue_category": (
        "What best describes your issue?\n"
        "• Non-Delivery\n• Damaged/Defective Item\n• Wrong/Missing Item\n"
        "• Refund Delayed/Denied\n• Hidden Charges/Overbilling\n"
        "• Expired Food/Quick-Commerce Issue\n• Other"
    ),
    "amount": "What was the order/transaction amount (in ₹)?",
    "incident_date": "When did the incident occur (e.g. 2026-10-15)?",
    "customer_support_contacted": "Have you already contacted the platform's customer support? (yes/no)",
    "evidence_uploaded": "Do you have screenshots, invoices, or other evidence to upload?",
    "resolution_sought": "What resolution are you seeking (refund, replacement, compensation, etc.)?",
}

_ENTITY_SLOT_MAP: Dict[str, str] = {
    "PLATFORM": "platform",
    "ORDER_ID": "order_id",
    "ISSUE_CATEGORY": "issue_category",
    "AMOUNT": "amount",
    "DATE": "incident_date",
    "CUSTOMER_SUPPORT_CONTACTED": "customer_support_contacted",
    "RESOLUTION": "resolution_sought",
}


def _cast_slot_value(slot_name: str, raw_value: str) -> Any:
    """Coerce extracted string to the type expected by the Case column."""
    if slot_name == "amount":
        try:
            cleaned = str(raw_value).replace(",", "").replace("₹", "").replace("Rs", "").strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    if slot_name == "incident_date":
        norm = normalize_date(str(raw_value))
        return norm or str(raw_value).strip()
    if slot_name == "customer_support_contacted":
        return str(raw_value).strip().lower() in {"yes", "true", "1", "y"}
    if slot_name == "evidence_uploaded":
        return str(raw_value).strip().lower() in {"yes", "true", "1", "y"}
    if slot_name == "issue_category":
        for cat in IssueCategory:
            if str(raw_value).strip().lower() in (cat.value.lower(), cat.name.lower()):
                return cat.value
        return str(raw_value).strip()
    return str(raw_value).strip()


_STAGE_ORDER: List[WorkflowStage] = [
    WorkflowStage.INTAKE,
    WorkflowStage.CLASSIFICATION,
    WorkflowStage.SLOT_FILLING,
    WorkflowStage.EVIDENCE_INGESTION,
    WorkflowStage.TIMELINE_RECONSTRUCTION,
    WorkflowStage.CONFLICT_VERIFICATION,
    WorkflowStage.TIER1_DRAFT,
    WorkflowStage.PLATFORM_TRACKING,
    WorkflowStage.TIER2_READINESS,
    WorkflowStage.NCH_DOCKET,
    WorkflowStage.TIER3_CHECKLIST,
    WorkflowStage.FINAL_FILING,
]


def _determine_stage(case: Case, missing: List[str]) -> WorkflowStage:
    """Decide stage based on slot completeness."""
    current = case.workflow_stage

    if not case.issue_category:
        if current == WorkflowStage.INTAKE.value:
            return WorkflowStage.CLASSIFICATION
        return WorkflowStage(current)

    if missing:
        return WorkflowStage.SLOT_FILLING

    return WorkflowStage.EVIDENCE_INGESTION


# ── Dialogue Manager ──────────────────────────────────────────────────────

class DialogueManager:
    """Tracks dialogue state, coordinates LLM conversational routing, fills slots,
    and advances workflow stages."""

    def process_message(
        self,
        case: Case,
        user_message: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Process an incoming user message and return updated state."""
        clean_text_lower = user_message.strip().lower()

        # 1. Real-time LLM Routing & Intent Detection ──────────────────────
        llm_res = chat_with_llm(case, user_message, db)
        intent_action = llm_res.get("intent_action", "general_chat")
        bot_message = llm_res.get("bot_message", "")
        llm_slots = llm_res.get("extracted_slots", {})

        llm_live = llm_res.get("provider_used") in ("gemini", "openai")
        logger.info(f"LLM routed intent '{intent_action}' with provider '{llm_res.get('provider_used')}'")

        # 2. Handle Advance / Skip Intent ──────────────────────────────────
        wants_advance = intent_action == "advance_stage" or (
            intent_action != "answer_query" and _ADVANCE_RE.search(clean_text_lower)
        )
        if wants_advance and case.workflow_stage in _EARLY_STAGES and self._get_missing_slots(case):
            # Stage gate: the core case facts must exist before evidence/drafting stages.
            missing = self._get_missing_slots(case)
            bot_reply = (
                "Before we move on I still need a few case details, so the notice is accurate. "
                + SLOT_QUESTIONS.get(missing[0], f"Could you share the {missing[0].replace('_', ' ')}?")
            )
            return self._record_turns_and_return(case, user_message, bot_reply, intent="advance_blocked", slots_updated={}, db=db)
        if wants_advance:
            if case.workflow_stage == WorkflowStage.EVIDENCE_INGESTION.value:
                case.workflow_stage = WorkflowStage.TIMELINE_RECONSTRUCTION.value
                from app.services.timeline_evidence_engine import TimelineEngine
                tl_engine = TimelineEngine()
                events = tl_engine.build_timeline(case.id, db)
                tl_engine.detect_conflicts(case.id, db)

                bot_reply = (
                    f"Understood! Advancing to **Stage 5: Timeline Reconstruction**.\n\n"
                    f"I have synthesized **{len(events)} chronological timeline events** from your case facts and evidence documents. "
                    f"You can review the chronological sequence and audit checks in the **Timeline** tab."
                )
            else:
                # Advance to next stage in STAGE_ORDER
                cur_val = case.workflow_stage
                next_val = None
                for i, st in enumerate(_STAGE_ORDER):
                    if st.value == cur_val and i < len(_STAGE_ORDER) - 1:
                        next_val = _STAGE_ORDER[i + 1].value
                        break
                if next_val:
                    case.workflow_stage = next_val
                    bot_reply = f"Advancing to **{next_val}**.\n\n{bot_message}"
                else:
                    bot_reply = bot_message or "Case is already at the final stage."

            return self._record_turns_and_return(case, user_message, bot_reply, intent="advance_stage", slots_updated={}, db=db)

        # 3. Handle Question Answering (e.g., "ok what to do in stage 5") ──
        if intent_action == "answer_query" or (
            not llm_live
            and any(q in clean_text_lower for q in ["what", "how", "explain", "tell me", "can i", "why"])
            and not any(slot_k in clean_text_lower for slot_k in ["order id is", "ref is", "amount is", "placed at"])
        ):
            reply = bot_message or "Good question. I'm keeping all your case details as they are."
            missing = self._get_missing_slots(case)
            if not llm_live and case.workflow_stage in _EARLY_STAGES and missing:
                reply += "\n\nWhenever you're ready: " + SLOT_QUESTIONS.get(missing[0], "")
            return self._record_turns_and_return(
                case, user_message, reply, intent="answer_query", slots_updated={}, db=db
            )

        # 4. Handle Contextual Evidence Waiver (e.g. COD / Cash on Delivery)
        if intent_action == "waive_evidence" or (not llm_live and is_cod_message(clean_text_lower)):
            from app.services.timeline_evidence_engine import EvidenceEngine
            ev_engine = EvidenceEngine()

            checklist = dict(case.evidence_gap_checklist or {})
            checklist["Payment proof (bank/UPI statement)"] = True
            checklist["Bank statement showing no credit"] = True
            case.evidence_gap_checklist = checklist
            flag_modified(case, "evidence_gap_checklist")
            db.commit()

            gap_res = ev_engine.compute_gap_analysis(case.id, db)
            readiness = gap_res.get("readiness_score", 0.0)
            missing_req = [r for r in gap_res.get("required", []) if not gap_res.get("checklist", {}).get(r) and r != "Payment proof (bank/UPI statement)"]

            if missing_req:
                next_act = f"We still need: **{missing_req[0]}**. Please attach it with **`+`**, or click **[Skip / Proceed to Stage 5]**."
            else:
                next_act = "All required items are verified or waived! You can proceed to **Stage 5: Timeline Reconstruction**."

            bot_reply = (
                f"Understood! Since this order was paid via **Cash on Delivery (COD)**, the bank/UPI statement requirement has been waived.\n\n"
                f"**Updated Case Readiness Score:** {readiness}%\n\n"
                f"{next_act}"
            )
            return self._record_turns_and_return(case, user_message, bot_reply, intent="waive_evidence", slots_updated={}, db=db)

        # 5. Handle Document Categorization Correction ────────────────────
        if intent_action == "correct_category" or (
            any(ci in clean_text_lower for ci in ["no that", "that was", "that is", "that's", "this was", "this is", "correct it to"])
            and any(kw in clean_text_lower for kw in ["invoice", "bill", "receipt", "support chat", "bank statement", "payment proof"])
        ):
            new_cat = llm_slots.get("document_type")
            if not new_cat:
                if any(k in clean_text_lower for k in ["invoice", "bill", "receipt", "summary"]):
                    new_cat = "Order confirmation / invoice"
                elif any(k in clean_text_lower for k in ["support", "chat", "agent"]):
                    new_cat = "Chat with customer support"
                elif any(k in clean_text_lower for k in ["refund", "rejection", "status"]):
                    new_cat = "Refund request/status screenshot"
                elif any(k in clean_text_lower for k in ["payment", "bank", "upi", "statement"]):
                    new_cat = "Payment proof (bank/UPI statement)"
                else:
                    new_cat = "Photo of received item vs ordered item"

            last_doc = (
                db.query(EvidenceDocument)
                .filter(EvidenceDocument.case_id == case.id)
                .order_by(EvidenceDocument.upload_timestamp.desc())
                .first()
            )
            if last_doc:
                fields = dict(last_doc.extracted_fields or {})
                fields["document_type"] = new_cat
                last_doc.extracted_fields = fields
                flag_modified(last_doc, "extracted_fields")
                db.commit()

                from app.services.timeline_evidence_engine import EvidenceEngine
                gap_res = EvidenceEngine().compute_gap_analysis(case.id, db)
                readiness = gap_res.get("readiness_score", 0.0)

                bot_reply = (
                    f"I have updated the categorization of `{last_doc.filename}` to **{new_cat}**.\n\n"
                    f"**Updated Case Readiness Score:** {readiness}%"
                )
                return self._record_turns_and_return(case, user_message, bot_reply, intent="correct_category", slots_updated={}, db=db)

        # 6. NLP Entity Extraction & Slot Filling ─────────────────────────
        intent_result = classify_complaint(user_message)
        entities = extract_entities(user_message)

        intent = intent_result.get("intent") or intent_result.get("category", "unknown")
        confidence = intent_result.get("confidence", 0.0)

        slots_updated: Dict[str, Any] = {}

        # Normalize any relief/remedy slot aliases from LLM
        for alias in ("relief_sought", "remedy", "relief", "resolution", "remedy_sought", "relief_remedy"):
            if alias in llm_slots:
                val = llm_slots.pop(alias)
                if val and "resolution_sought" not in llm_slots:
                    llm_slots["resolution_sought"] = val

        # Merge slots from LLM output first. The LLM is told to return only values
        # stated in this message, so a value here is new info or an explicit correction.
        for k, v in llm_slots.items():
            if v is not None and k in SLOT_NAMES and hasattr(case, k):
                casted = v if isinstance(v, bool) else _cast_slot_value(k, str(v))
                if casted is not None and casted != getattr(case, k, None):
                    setattr(case, k, casted)
                    slots_updated[k] = casted

        # Rule-based extraction below is the offline fallback only; when the LLM ran,
        # it already disambiguated platform/amount in context and must not be overridden.
        is_correction = bool(_CORRECTION_RE.search(clean_text_lower))
        def _can_set(slot: str) -> bool:
            if llm_live or slot in slots_updated:
                return False
            return getattr(case, slot, None) in (None, "") or is_correction

        # Check what the assistant last asked for
        last_turn = (
            db.query(DialogueTurn)
            .filter(DialogueTurn.case_id == case.id, DialogueTurn.role == "assistant")
            .order_by(DialogueTurn.turn_number.desc())
            .first()
        )
        expected_slot = None
        if last_turn and last_turn.message:
            last_text = last_turn.message.lower()
            if "resolution" in last_text or "seeking" in last_text or "refund, replacement" in last_text or "remedy" in last_text:
                expected_slot = "resolution_sought"
            elif "order id" in last_text or "reference number" in last_text:
                expected_slot = "order_id"
            elif "platform" in last_text or "which e-commerce" in last_text:
                expected_slot = "platform"
            elif "amount" in last_text or "transaction" in last_text:
                expected_slot = "amount"
            elif "incident" in last_text or "occur" in last_text or "when" in last_text:
                expected_slot = "incident_date"

        # Semantic Resolution / Relief (Remedy) Slot Extraction
        if _can_set("resolution_sought"):
            if expected_slot == "resolution_sought" or any(w in clean_text_lower for w in ["inform", "feedback", "nothing", "refund", "replace", "compensation", "apology", "just inform", "no money", "no refund"]):
                if any(w in clean_text_lower for w in ["inform", "nothing", "feedback", "notice", "aware"]):
                    res_val = "Inform the platform / No monetary claim"
                elif "refund" in clean_text_lower:
                    res_val = "Full refund"
                elif "replace" in clean_text_lower or "exchange" in clean_text_lower:
                    res_val = "Product replacement"
                elif "compensation" in clean_text_lower or "damages" in clean_text_lower:
                    res_val = "Compensation for inconvenience/loss"
                else:
                    res_val = user_message.strip()[:100]

                case.resolution_sought = res_val
                slots_updated["resolution_sought"] = res_val

        # Platform resolution
        platform_entities = [e for e in entities if e.get("type") == "PLATFORM"]
        amount_entities = [e for e in entities if e.get("type") == "AMOUNT"]
        other_entities = [e for e in entities if e.get("type") not in ("PLATFORM", "AMOUNT")]

        if _can_set("platform"):
            platform_candidates = [p["value"] for p in platform_entities]
            resolved_plat = resolve_platform(user_message, platform_candidates)
            if resolved_plat:
                case.platform = resolved_plat
                slots_updated["platform"] = resolved_plat

        # Amount disambiguation
        if _can_set("amount"):
            resolved_amt = disambiguate_amount(user_message, entities)
            if resolved_amt is not None:
                case.amount = resolved_amt
                slots_updated["amount"] = resolved_amt

        # Order ID pattern matching
        if _can_set("order_id"):
            order_entities = [e for e in entities if e.get("type") == "ORDER_ID"]
            if order_entities:
                case.order_id = order_entities[0]["value"]
                slots_updated["order_id"] = order_entities[0]["value"]
            else:
                oid_m = re.search(r"(?:order\s*(?:id|#|no\.?)\s*[:=\-]?\s*)([A-Za-z0-9_\-]+)", user_message, re.IGNORECASE)
                if oid_m:
                    case.order_id = oid_m.group(1).strip()
                    slots_updated["order_id"] = case.order_id

        # Other entities
        for ent in other_entities:
            etype = ent.get("type", "")
            evalue = ent.get("value", "")
            slot_name = _ENTITY_SLOT_MAP.get(etype)
            norm_val = ent.get("normalized_value") or ent.get("normalized") or evalue

            db.add(ExtractedEntity(
                case_id=case.id,
                entity_type=etype,
                entity_value=evalue,
                normalized_value=norm_val,
                source="chat",
                confidence=ent.get("confidence", 1.0),
            ))

            if slot_name and _can_set(slot_name):
                if True:
                    val_to_cast = norm_val if slot_name == "incident_date" else evalue
                    casted = _cast_slot_value(slot_name, val_to_cast)
                    if casted is not None:
                        setattr(case, slot_name, casted)
                        slots_updated[slot_name] = casted

        if not llm_live and not case.issue_category and intent != "unknown":
            for cat in IssueCategory:
                if intent.lower() in (cat.value.lower(), cat.name.lower()):
                    case.issue_category = cat.value
                    slots_updated["issue_category"] = cat.value
                    break

        # 7. Workflow Stage Progression ───────────────────────────────────
        prev_stage = case.workflow_stage
        missing = self._get_missing_slots(case)

        # Only auto-advance stages if currently in early intake/slot filling
        if case.workflow_stage in (WorkflowStage.INTAKE.value, WorkflowStage.CLASSIFICATION.value, WorkflowStage.SLOT_FILLING.value):
            new_stage = _determine_stage(case, missing)
            case.workflow_stage = new_stage.value

        # 8. Generate Assistant Response ──────────────────────────────────
        if case.workflow_stage == WorkflowStage.SLOT_FILLING.value and missing:
            # Gemini already sees the missing-slot list; use its natural reply when live.
            assistant_message = (bot_message if llm_live and bot_message
                                 else self._build_slot_prompt(case, missing, slots_updated))
        elif case.workflow_stage == WorkflowStage.EVIDENCE_INGESTION.value:
            if prev_stage == WorkflowStage.SLOT_FILLING.value or not missing:
                assistant_message = self._build_stage4_intro(case, slots_updated)
            else:
                from app.services.timeline_evidence_engine import EvidenceEngine
                gap_res = EvidenceEngine().compute_gap_analysis(case.id, db)
                readiness = gap_res.get("readiness_score", 0.0)
                missing_req = [r for r in gap_res.get("required", []) if not gap_res.get("checklist", {}).get(r)]
                if missing_req:
                    assistant_message = (
                        f"Noted: \"{user_message}\". We are at **Stage 4: Evidence Ingestion** (Readiness: **{readiness}%**).\n\n"
                        f"To strengthen your case, please attach **{missing_req[0]}** with **`+`**, or click **[Skip / Proceed to Stage 5]**."
                    )
                else:
                    assistant_message = (
                        f"All key evidence has been received (Readiness: **{readiness}%**)! "
                        f"Click **[Proceed to Stage 5: Timeline Reconstruction]** when ready."
                    )
        else:
            assistant_message = bot_message or f"Understood. We are at **{case.workflow_stage}**."


        return self._record_turns_and_return(
            case, user_message, assistant_message, intent=intent, slots_updated=slots_updated, db=db
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_missing_slots(self, case: Case) -> List[str]:
        missing: List[str] = []
        for slot in REQUIRED_SLOTS:
            val = getattr(case, slot, None)
            if val is None or val == "":
                missing.append(slot)
        return missing

    def _build_slot_prompt(self, case: Case, missing: List[str], slots_updated: Dict[str, Any]) -> str:
        parts: List[str] = []
        if slots_updated:
            ack_items = ", ".join(f"{k.replace('_', ' ')}: **{v}**" for k, v in slots_updated.items())
            parts.append(f"Got it — I've noted {ack_items}.")

        if missing:
            first_missing = missing[0]
            question = SLOT_QUESTIONS.get(first_missing, f"Could you provide your {first_missing.replace('_', ' ')}?")
            parts.append(question)
        return "\n\n".join(parts)

    def _build_stage4_intro(self, case: Case, slots_updated: Dict[str, Any]) -> str:
        from app.services.timeline_evidence_engine import EVIDENCE_REQUIREMENTS
        cat = case.issue_category or "Other"
        reqs = EVIDENCE_REQUIREMENTS.get(cat, EVIDENCE_REQUIREMENTS.get("Other", {}))
        req_list = reqs.get("required", ["Order confirmation / invoice", "Payment proof (bank/UPI statement)"])
        rec_list = reqs.get("recommended", ["Chat with customer support"])

        doc_lines = []
        for i, r in enumerate(req_list, 1):
            doc_lines.append(f"{i}. **{r}** *(Required)*")
        for i, r in enumerate(rec_list, len(req_list) + 1):
            doc_lines.append(f"{i}. **{r}** *(Optional)*")

        docs_formatted = "\n".join(doc_lines)
        ack = ""
        if slots_updated:
            ack_items = ", ".join(f"{k.replace('_', ' ')}: **{v}**" for k, v in slots_updated.items())
            ack = f"Got it — noted {ack_items}!\n\n"

        return (
            f"{ack}Thank you — I have noted all key grievance facts! We are now at **Stage 4: Evidence Ingestion & OCR**.\n\n"
            f"To build an evidence-grounded case for **{cat}**, please attach or upload your supporting files:\n\n"
            f"{docs_formatted}\n\n"
            f"📎 *Click the **`+` Attach** button below to upload directly in chat, or click **[Skip / Proceed to Stage 5]** if you don't have them.*"
        )

    def _record_turns_and_return(
        self,
        case: Case,
        user_msg: str,
        bot_reply: str,
        intent: str,
        slots_updated: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        """Record dialogue turns in database and construct API return payload."""
        turn_count = db.query(DialogueTurn).filter(DialogueTurn.case_id == case.id).count()

        db.add(DialogueTurn(
            case_id=case.id,
            turn_number=turn_count + 1,
            role="user",
            message=user_msg,
            slots_updated=slots_updated if slots_updated else None,
            intent_detected=intent,
            confidence=1.0,
        ))
        db.add(DialogueTurn(
            case_id=case.id,
            turn_number=turn_count + 2,
            role="assistant",
            message=bot_reply,
            intent_detected=None,
            confidence=None,
        ))
        db.commit()
        db.refresh(case)

        clean_entities = []
        if case.platform: clean_entities.append({"type": "PLATFORM", "value": case.platform})
        if case.order_id: clean_entities.append({"type": "ORDER_ID", "value": case.order_id})
        if case.amount: clean_entities.append({"type": "AMOUNT", "value": f"₹{case.amount}"})
        if case.incident_date: clean_entities.append({"type": "DATE", "value": str(case.incident_date)})
        if case.issue_category: clean_entities.append({"type": "CATEGORY", "value": case.issue_category})

        missing = self._get_missing_slots(case)

        return {
            "turn_number": turn_count + 2,
            "assistant_message": bot_reply,
            "slots": {
                "platform": case.platform,
                "order_id": case.order_id,
                "issue_category": case.issue_category,
                "amount": case.amount,
                "incident_date": case.incident_date,
                "customer_support_contacted": case.customer_support_contacted,
                "evidence_uploaded": case.evidence_uploaded,
                "resolution_sought": case.resolution_sought,
            },
            "missing_slots": missing,
            "intent": intent,
            "confidence": 1.0,
            "entities_extracted": clean_entities,
            "workflow_stage": case.workflow_stage,
        }
