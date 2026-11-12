"""Timeline reconstruction and evidence gap-analysis engines."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import (
    Case, DialogueTurn, EvidenceDocument, ExtractedEntity,
    IssueCategory, TimelineEvent,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# TimelineEngine
# ═══════════════════════════════════════════════════════════════════════════

class TimelineEngine:
    """Builds, maintains, and validates the chronological timeline of a case
    by merging user-reported events with OCR-extracted dates from documents."""

    # ── public API ──────────────────────────────────────────────────────

    def build_timeline(self, case_id: str, db: Session) -> List[Dict[str, Any]]:
        """Build a sorted list of timeline events from dialogue turns and
        uploaded documents for the given case.

        Returns a list of dicts sorted by event_date ascending.
        """
        # Fetch existing persisted events
        existing_events = (
            db.query(TimelineEvent)
            .filter(TimelineEvent.case_id == case_id)
            .all()
        )

        existing_descs = {e.description for e in existing_events}

        # Check primary case incident_date and order details
        case = db.query(Case).filter(Case.id == case_id).first()
        if case and case.incident_date:
            desc = f"Order Placed / Incident on {case.platform or 'Platform'}: Order #{case.order_id or 'N/A'}"
            if desc not in existing_descs:
                evt = TimelineEvent(
                    case_id=case_id,
                    event_date=str(case.incident_date),
                    event_type="order_placed",
                    description=desc,
                    source="case_record",
                )
                db.add(evt)
                existing_events.append(evt)
                existing_descs.add(desc)

        # Also mine dialogue turns for date-bearing entities we haven't
        # turned into events yet.
        date_entities = (
            db.query(ExtractedEntity)
            .filter(
                ExtractedEntity.case_id == case_id,
                ExtractedEntity.entity_type == "DATE",
            )
            .all()
        )

        for ent in date_entities:
            desc = f"Date mentioned in chat: {ent.entity_value}"
            if desc not in existing_descs:
                evt = TimelineEvent(
                    case_id=case_id,
                    event_date=ent.normalized_value or ent.entity_value,
                    event_type="user_reported",
                    description=desc,
                    source="user_reported",
                )
                db.add(evt)
                existing_events.append(evt)
                existing_descs.add(desc)

        # Mine OCR-extracted dates from evidence documents
        docs = (
            db.query(EvidenceDocument)
            .filter(
                EvidenceDocument.case_id == case_id,
                EvidenceDocument.processing_status == "processed",
            )
            .all()
        )
        for doc in docs:
            if doc.extracted_fields and isinstance(doc.extracted_fields, dict):
                for field_key, field_val in doc.extracted_fields.items():
                    if "date" in field_key.lower() and field_val:
                        desc = f"OCR from {doc.filename}: {field_key}={field_val}"
                        if desc not in existing_descs:
                            evt = TimelineEvent(
                                case_id=case_id,
                                event_date=str(field_val),
                                event_type="ocr_extracted",
                                description=desc,
                                source="ocr_extracted",
                            )
                            db.add(evt)
                            existing_events.append(evt)
                            existing_descs.add(desc)

        db.commit()

        # Sort by event_date (string sort works for ISO dates; fall back to
        # event_date_normalized when available)
        def _sort_key(e: TimelineEvent):
            if e.event_date_normalized:
                return e.event_date_normalized
            try:
                return datetime.fromisoformat(e.event_date)
            except (ValueError, TypeError):
                return datetime.max

        existing_events.sort(key=_sort_key)

        return [
            {
                "id": e.id,
                "event_date": e.event_date,
                "event_date_normalized": (
                    e.event_date_normalized.isoformat()
                    if e.event_date_normalized
                    else None
                ),
                "event_type": e.event_type,
                "description": e.description,
                "source": e.source,
                "has_conflict": e.has_conflict,
                "conflict_details": e.conflict_details,
            }
            for e in existing_events
        ]

    def detect_conflicts(self, case_id: str, db: Session) -> List[Dict[str, Any]]:
        """Detect conflicts: date mismatches or amount discrepancies
        between user claims and OCR-extracted data.

        Returns a list of conflict dicts.
        """
        conflicts: List[Dict[str, Any]] = []

        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return conflicts

        events = (
            db.query(TimelineEvent)
            .filter(TimelineEvent.case_id == case_id)
            .all()
        )

        # 1. Date conflicts: compare user-reported dates vs OCR dates
        user_dates: List[str] = []
        ocr_dates: List[str] = []
        for evt in events:
            if evt.source == "user_reported":
                user_dates.append(evt.event_date)
            elif evt.source == "ocr_extracted":
                ocr_dates.append(evt.event_date)

        # Simple: flag if an OCR date does not appear anywhere in user dates
        for od in ocr_dates:
            if od not in user_dates:
                conflict = {
                    "type": "date_mismatch",
                    "description": (
                        f"OCR-extracted date '{od}' does not match any "
                        f"user-reported date ({', '.join(user_dates) or 'none reported'})"
                    ),
                    "user_dates": user_dates,
                    "ocr_date": od,
                }
                conflicts.append(conflict)

        # 2. Amount discrepancies
        ocr_amounts: List[float] = []
        amount_entities = (
            db.query(ExtractedEntity)
            .filter(
                ExtractedEntity.case_id == case_id,
                ExtractedEntity.entity_type == "AMOUNT",
                ExtractedEntity.source == "ocr",
            )
            .all()
        )
        for ae in amount_entities:
            try:
                val = float(ae.entity_value.replace(",", "").replace("₹", "").replace("Rs", "").strip())
                ocr_amounts.append(val)
            except (ValueError, TypeError):
                pass

        if case.amount and ocr_amounts:
            for oa in ocr_amounts:
                if abs(oa - case.amount) > 0.01:
                    conflict = {
                        "type": "amount_discrepancy",
                        "description": (
                            f"User-claimed amount ₹{case.amount} differs from "
                            f"OCR-extracted amount ₹{oa}"
                        ),
                        "user_amount": case.amount,
                        "ocr_amount": oa,
                    }
                    conflicts.append(conflict)

        # Mark conflicting events in DB
        for evt in events:
            for c in conflicts:
                if c["type"] == "date_mismatch" and evt.event_date == c.get("ocr_date"):
                    evt.has_conflict = True
                    evt.conflict_details = c["description"]

        db.commit()
        return conflicts

    def add_event(
        self,
        case_id: str,
        event_date: str,
        event_type: str,
        description: str,
        source: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Add a single timeline event and return its dict representation."""
        normalized: Optional[datetime] = None
        try:
            normalized = datetime.fromisoformat(event_date)
        except (ValueError, TypeError):
            pass

        evt = TimelineEvent(
            case_id=case_id,
            event_date=event_date,
            event_date_normalized=normalized,
            event_type=event_type,
            description=description,
            source=source,
        )
        db.add(evt)
        db.commit()
        db.refresh(evt)

        return {
            "id": evt.id,
            "event_date": evt.event_date,
            "event_date_normalized": (
                evt.event_date_normalized.isoformat()
                if evt.event_date_normalized
                else None
            ),
            "event_type": evt.event_type,
            "description": evt.description,
            "source": evt.source,
            "has_conflict": evt.has_conflict,
            "conflict_details": evt.conflict_details,
        }


# ═══════════════════════════════════════════════════════════════════════════
# EvidenceEngine
# ═══════════════════════════════════════════════════════════════════════════

# Evidence requirements per issue category.
# "required" must be present for full readiness; "recommended" improves case.
EVIDENCE_REQUIREMENTS: Dict[str, Dict[str, List[str]]] = {
    IssueCategory.NON_DELIVERY.value: {
        "required": [
            "Order confirmation / invoice",
            "Delivery status screenshot",
            "Payment proof (bank/UPI statement)",
        ],
        "recommended": [
            "Chat with customer support",
            "Platform tracking page screenshot",
        ],
    },
    IssueCategory.DAMAGED_DEFECTIVE.value: {
        "required": [
            "Order confirmation / invoice",
            "Photo of damaged/defective product",
            "Payment proof (bank/UPI statement)",
        ],
        "recommended": [
            "Unboxing video",
            "Chat with customer support",
            "Return/replacement request screenshot",
        ],
    },
    IssueCategory.WRONG_MISSING.value: {
        "required": [
            "Order confirmation / invoice",
            "Photo of received item vs ordered item",
            "Payment proof (bank/UPI statement)",
        ],
        "recommended": [
            "Chat with customer support",
            "Packaging/label photo",
        ],
    },
    IssueCategory.REFUND_DELAYED.value: {
        "required": [
            "Order confirmation / invoice",
            "Refund request/status screenshot",
            "Payment proof (bank/UPI statement)",
        ],
        "recommended": [
            "Bank statement showing no credit",
            "Chat with customer support",
            "Platform refund policy screenshot",
        ],
    },
    IssueCategory.HIDDEN_CHARGES.value: {
        "required": [
            "Order confirmation / invoice showing original price",
            "Payment proof showing charged amount",
            "Screenshot of price at time of purchase",
        ],
        "recommended": [
            "Platform T&C / pricing page archive",
            "Chat with customer support",
        ],
    },
    IssueCategory.EXPIRED_FOOD.value: {
        "required": [
            "Order confirmation / invoice",
            "Photo of expired product with expiry date visible",
            "Payment proof (bank/UPI statement)",
        ],
        "recommended": [
            "Photo of packaging/batch number",
            "Chat with customer support",
            "Medical report if health affected",
        ],
    },
    IssueCategory.OTHER.value: {
        "required": [
            "Order confirmation / invoice",
            "Payment proof (bank/UPI statement)",
            "Screenshot of the issue",
        ],
        "recommended": [
            "Chat with customer support",
            "Any other relevant documentation",
        ],
    },
}


class EvidenceEngine:
    """Evaluates submitted evidence against category-specific requirements
    and computes a readiness score with a gap-analysis checklist."""

    def compute_gap_analysis(
        self, case_id: str, db: Session
    ) -> Dict[str, Any]:
        """Compute evidence gap analysis for the case.

        Returns:
            {required, submitted, missing, readiness_score, checklist}
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return {
                "required": [],
                "submitted": [],
                "missing": [],
                "readiness_score": 0.0,
                "checklist": {},
            }

        category = case.issue_category or IssueCategory.OTHER.value
        reqs = EVIDENCE_REQUIREMENTS.get(
            category, EVIDENCE_REQUIREMENTS[IssueCategory.OTHER.value]
        )
        required_docs: List[str] = reqs["required"]
        recommended_docs: List[str] = reqs.get("recommended", [])
        all_needed = required_docs + recommended_docs

        # Fetch submitted documents
        docs = (
            db.query(EvidenceDocument)
            .filter(EvidenceDocument.case_id == case_id)
            .all()
        )

        submitted_names = [d.filename for d in docs]
        submitted_types = set()
        for doc in docs:
            fname_lower = doc.filename.lower()
            for needed in all_needed:
                # Simple keyword match between filename and requirement
                keywords = needed.lower().split()
                # If at least half the significant words match
                significant = [w for w in keywords if len(w) > 3]
                matches = sum(1 for w in significant if w in fname_lower)
                if significant and matches >= max(1, len(significant) // 2):
                    submitted_types.add(needed)
            # Also check OCR extracted_fields for doc type hints
            if doc.extracted_fields and isinstance(doc.extracted_fields, dict):
                doc_type = doc.extracted_fields.get("document_type", "")
                if doc_type:
                    dt_low = doc_type.lower()
                    for needed in all_needed:
                        n_low = needed.lower()
                        if dt_low in n_low or n_low in dt_low:
                            submitted_types.add(needed)
                        elif ("invoice" in dt_low or "bill" in dt_low or "receipt" in dt_low) and "invoice" in n_low:
                            submitted_types.add(needed)
                        elif ("support" in dt_low or "chat" in dt_low) and "support" in n_low:
                            submitted_types.add(needed)
                        elif ("refund" in dt_low or "status" in dt_low) and "refund" in n_low:
                            submitted_types.add(needed)
                        elif ("payment" in dt_low or "upi" in dt_low or "bank" in dt_low) and "payment" in n_low:
                            submitted_types.add(needed)

        # Check if Cash on Delivery (COD) was reported in turns or case records
        is_cod = False
        user_msgs = [t.message.lower() for t in case.dialogue_turns if t.role == "user" and t.message]
        if any("cod" in m or "cash on delivery" in m or "paid by cash" in m or "paid as cod" in m or "cash payment" in m for m in user_msgs):
            is_cod = True
        if case.evidence_gap_checklist and case.evidence_gap_checklist.get("Payment proof (bank/UPI statement)"):
            is_cod = True

        if is_cod:
            # Payment proof via bank/UPI statement is impossible and waived for COD
            submitted_types.add("Payment proof (bank/UPI statement)")
            submitted_types.add("Bank statement showing no credit")

        submitted = sorted(submitted_types)
        missing = [r for r in all_needed if r not in submitted_types]
        checklist = {item: item in submitted_types for item in all_needed}

        # Score: required docs weigh 80%, recommended 20%
        req_count = len(required_docs)
        rec_count = len(recommended_docs)

        req_submitted = sum(1 for r in required_docs if r in submitted_types)
        rec_submitted = sum(1 for r in recommended_docs if r in submitted_types)

        if req_count > 0:
            req_pct = (req_submitted / req_count) * 80
        else:
            req_pct = 80.0

        if rec_count > 0:
            rec_pct = (rec_submitted / rec_count) * 20
        else:
            rec_pct = 20.0

        readiness_score = round(req_pct + rec_pct, 1)

        # Persist to case
        case.case_readiness_score = readiness_score
        case.evidence_gap_checklist = checklist
        case.evidence_uploaded = len(docs) > 0
        db.commit()

        return {
            "required": all_needed,
            "submitted": submitted,
            "missing": missing,
            "readiness_score": readiness_score,
            "checklist": checklist,
        }
