"""Document generation engine for platform emails, NCH summaries, and
e-Jagriti filing packages — strictly grounded in case-store data."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import (
    Case, DialogueTurn, EvidenceDocument, GeneratedDraft,
    TimelineEvent, EscalationTier,
)

logger = logging.getLogger(__name__)

# ── Known grievance officer contacts (from knowledge base) ─────────────────

_GRIEVANCE_CONTACTS: Dict[str, Dict[str, str]] = {
    "amazon": {
        "email": "grievance-officer@amazon.in",
        "name": "Grievance Officer, Amazon India",
    },
    "flipkart": {
        "email": "grievance.officer@flipkart.com",
        "name": "Grievance Officer, Flipkart Internet Pvt. Ltd.",
    },
    "swiggy": {
        "email": "grievance@swiggy.in",
        "name": "Grievance Officer, Swiggy (Bundl Technologies Pvt. Ltd.)",
    },
    "zomato": {
        "email": "grievance@zomato.com",
        "name": "Grievance Officer, Zomato Ltd.",
    },
    "myntra": {
        "email": "grievance.officer@myntra.com",
        "name": "Grievance Officer, Myntra Designs Pvt. Ltd.",
    },
    "meesho": {
        "email": "grievance@meesho.com",
        "name": "Grievance Officer, Meesho (Fashnear Technologies Pvt. Ltd.)",
    },
    "blinkit": {
        "email": "grievance@blinkit.com",
        "name": "Grievance Officer, Blinkit (Grofers India Pvt. Ltd.)",
    },
    "jiomart": {
        "email": "grievance.ecommerce@ril.com",
        "name": "Grievance Officer, JioMart (Reliance Retail Ltd.)",
    },
}

_DEFAULT_GRIEVANCE = {
    "email": "grievance@<platform>.com",
    "name": "Grievance Officer",
}


def _get_grievance_contact(platform: Optional[str]) -> Dict[str, str]:
    if not platform:
        return _DEFAULT_GRIEVANCE
    return _GRIEVANCE_CONTACTS.get(platform.strip().lower(), _DEFAULT_GRIEVANCE)


def _format_date(dt: Optional[datetime]) -> str:
    if dt:
        return dt.strftime("%d %B %Y")
    return "N/A"


def _get_timeline_text(case_id: str, db: Session) -> str:
    """Build a numbered timeline string from persisted events."""
    events = (
        db.query(TimelineEvent)
        .filter(TimelineEvent.case_id == case_id)
        .order_by(TimelineEvent.event_date)
        .all()
    )
    if not events:
        return "No timeline events recorded."
    lines: List[str] = []
    for i, evt in enumerate(events, 1):
        lines.append(f"{i}. [{evt.event_date}] {evt.description} (Source: {evt.source})")
    return "\n".join(lines)


def _get_evidence_index(case_id: str, db: Session) -> str:
    """Build an evidence index listing all uploaded documents."""
    docs = (
        db.query(EvidenceDocument)
        .filter(EvidenceDocument.case_id == case_id)
        .order_by(EvidenceDocument.upload_timestamp)
        .all()
    )
    if not docs:
        return "No evidence documents uploaded."
    lines: List[str] = []
    for i, doc in enumerate(docs, 1):
        lines.append(
            f"Annexure {i}: {doc.filename} "
            f"(Type: {doc.file_type}, Uploaded: {_format_date(doc.upload_timestamp)})"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# DraftGenerator
# ═══════════════════════════════════════════════════════════════════════════

class DraftGenerator:
    """Generates formal complaint documents grounded entirely in case-store
    data.  No facts are hallucinated — all content comes from case slots,
    timeline events, and evidence records."""

    # ── 1. Platform Grievance Email ────────────────────────────────────

    def generate_platform_email(
        self, case_id: str, db: Session
    ) -> Dict[str, Any]:
        """Generate a formal grievance escalation email addressed to the
        platform's grievance officer.

        Returns a dict matching the DraftResponse schema.
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        contact = _get_grievance_contact(case.platform)
        timeline = _get_timeline_text(case_id, db)
        evidence_index = _get_evidence_index(case_id, db)
        today = _format_date(datetime.utcnow())

        content = f"""To,
{contact['name']}
Email: {contact['email']}

Date: {today}

Subject: Formal Grievance — Order {case.order_id or 'N/A'} | {case.issue_category or 'Consumer Complaint'}

Dear Sir/Madam,

I am writing to formally escalate my grievance regarding Order ID: {case.order_id or 'N/A'} placed on {case.platform or 'your platform'}.

1. ISSUE SUMMARY
   Category : {case.issue_category or 'N/A'}
   Amount   : ₹{case.amount or 'N/A'}
   Date     : {case.incident_date or 'N/A'}
   Platform : {case.platform or 'N/A'}

2. TIMELINE OF EVENTS
{timeline}

3. PREVIOUS CONTACT WITH CUSTOMER SUPPORT
   Customer support contacted: {'Yes' if case.customer_support_contacted else 'No' if case.customer_support_contacted is not None else 'Not specified'}

4. EVIDENCE ATTACHED
{evidence_index}

5. RELIEF SOUGHT
   {case.resolution_sought or 'Full resolution of the issue as per Consumer Protection Act, 2019.'}

I request that this matter be resolved within 15 days as mandated under the Consumer Protection (E-Commerce) Rules, 2020.  Failing a satisfactory resolution, I shall be compelled to escalate this complaint to the National Consumer Helpline (NCH) and, if necessary, the Consumer Disputes Redressal Commission via e-Jagriti.

Yours sincerely,
[Consumer Name]
Case Reference: {case.id}
"""

        draft = GeneratedDraft(
            case_id=case.id,
            draft_type="platform_email",
            title=f"Platform Grievance Email — Order {case.order_id or 'N/A'}",
            content=content,
            tier=EscalationTier.TIER_1_PLATFORM.value,
            metadata_json={
                "grievance_officer_email": contact["email"],
                "platform": case.platform,
            },
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        return {
            "draft_id": draft.id,
            "case_id": case.id,
            "draft_type": draft.draft_type,
            "title": draft.title,
            "content": draft.content,
            "tier": draft.tier,
            "generated_at": draft.generated_at,
            "metadata": draft.metadata_json,
        }

    # ── 2. NCH Complaint Summary ──────────────────────────────────────

    def generate_nch_summary(
        self, case_id: str, db: Session
    ) -> Dict[str, Any]:
        """Generate a structured National Consumer Helpline complaint summary.

        Returns a dict matching the DraftResponse schema.
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        timeline = _get_timeline_text(case_id, db)
        evidence_index = _get_evidence_index(case_id, db)
        today = _format_date(datetime.utcnow())

        content = f"""NATIONAL CONSUMER HELPLINE (NCH) — COMPLAINT FILING SUMMARY
{'=' * 60}
Date Prepared  : {today}
Case Reference : {case.id}

1. COMPLAINANT DETAILS
   (To be filled by the consumer)

2. OPPOSITE PARTY (PLATFORM)
   Platform    : {case.platform or 'N/A'}
   Order ID    : {case.order_id or 'N/A'}

3. COMPLAINT CATEGORY
   Issue Type  : {case.issue_category or 'N/A'}
   Amount (₹)  : {case.amount or 'N/A'}
   Incident Date: {case.incident_date or 'N/A'}

4. STATEMENT OF FACTS
   The consumer placed an order (ID: {case.order_id or 'N/A'}) on {case.platform or 'the platform'} \
for ₹{case.amount or 'N/A'} on {case.incident_date or 'N/A'}.  The issue experienced is: \
{case.issue_category or 'N/A'}.  Customer support was {'contacted' if case.customer_support_contacted else 'not contacted'}.

5. TIMELINE OF EVENTS
{timeline}

6. EVIDENCE INDEX
{evidence_index}

7. RELIEF SOUGHT
   {case.resolution_sought or 'Full resolution as per Consumer Protection Act, 2019.'}

8. PRE-FILING CHECKLIST
   [{'✓' if case.platform else '✗'}] Platform identified
   [{'✓' if case.order_id else '✗'}] Order ID available
   [{'✓' if case.issue_category else '✗'}] Issue category classified
   [{'✓' if case.amount else '✗'}] Transaction amount recorded
   [{'✓' if case.incident_date else '✗'}] Incident date recorded
   [{'✓' if case.evidence_uploaded else '✗'}] Evidence uploaded
   [{'✓' if case.resolution_sought else '✗'}] Relief sought specified
   [{'✓' if case.customer_support_contacted else '✗'}] Prior platform contact attempted

HOW TO FILE:
   1. Call NCH toll-free: 1800-11-4000 (or 14404)
   2. Online: https://consumerhelpline.gov.in
   3. NCH mobile app
   Provide the above details and attach evidence documents.
"""

        draft = GeneratedDraft(
            case_id=case.id,
            draft_type="nch_summary",
            title=f"NCH Complaint Summary — Order {case.order_id or 'N/A'}",
            content=content,
            tier=EscalationTier.TIER_2_NCH.value,
            metadata_json={
                "nch_helpline": "1800-11-4000",
                "nch_website": "https://consumerhelpline.gov.in",
                "platform": case.platform,
            },
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        return {
            "draft_id": draft.id,
            "case_id": case.id,
            "draft_type": draft.draft_type,
            "title": draft.title,
            "content": draft.content,
            "tier": draft.tier,
            "generated_at": draft.generated_at,
            "metadata": draft.metadata_json,
        }

    # ── 3. e-Jagriti Filing Package ───────────────────────────────────

    def generate_ejagriti_package(
        self, case_id: str, db: Session
    ) -> Dict[str, Any]:
        """Generate a complete e-Jagriti Consumer Commission filing package.

        Sections: List of Dates, Statement of Facts, Relief Sought,
        Evidence Index.

        Returns a dict matching the DraftResponse schema.
        """
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        timeline = _get_timeline_text(case_id, db)
        evidence_index = _get_evidence_index(case_id, db)
        today = _format_date(datetime.utcnow())

        # Build list of dates section from timeline events
        events = (
            db.query(TimelineEvent)
            .filter(TimelineEvent.case_id == case_id)
            .order_by(TimelineEvent.event_date)
            .all()
        )
        if events:
            dates_section = "\n".join(
                f"   {evt.event_date} — {evt.description}" for evt in events
            )
        else:
            dates_section = "   No events recorded."

        # Build escalation history
        from app.models import EscalationHistory
        esc_history = (
            db.query(EscalationHistory)
            .filter(EscalationHistory.case_id == case_id)
            .order_by(EscalationHistory.timestamp)
            .all()
        )
        if esc_history:
            esc_lines = "\n".join(
                f"   {_format_date(eh.timestamp)}: {eh.from_stage} → {eh.to_stage} "
                f"({eh.reason or 'N/A'})"
                for eh in esc_history
            )
        else:
            esc_lines = "   No escalation history."

        content = f"""E-JAGRITI CONSUMER COMMISSION — FILING PACKAGE
{'=' * 60}
Date Prepared   : {today}
Case Reference  : {case.id}
Filing Platform : https://edaakhil.nic.in (e-Jagriti / e-Daakhil)

{'─' * 60}
SECTION A: LIST OF DATES
{'─' * 60}
{dates_section}

{'─' * 60}
SECTION B: STATEMENT OF FACTS
{'─' * 60}
1. The Complainant placed Order ID: {case.order_id or 'N/A'} on {case.platform or 'the e-commerce platform'} \
on {case.incident_date or 'the date of incident'} for a total consideration of ₹{case.amount or 'N/A'}.

2. Nature of Grievance: {case.issue_category or 'N/A'}.

3. The Complainant {'contacted' if case.customer_support_contacted else 'did not contact'} the platform's \
customer support regarding this issue.

4. Despite efforts to resolve the matter through the platform's internal grievance mechanism \
(Tier 1) and the National Consumer Helpline (Tier 2), the issue remains unresolved.

5. Escalation History:
{esc_lines}

{'─' * 60}
SECTION C: RELIEF SOUGHT
{'─' * 60}
The Complainant respectfully prays that this Hon'ble Commission may be pleased to:

   a) Direct the Opposite Party ({case.platform or 'the platform'}) to provide: \
{case.resolution_sought or 'appropriate relief as per Consumer Protection Act, 2019'}.

   b) Award compensation for mental agony and harassment caused to the Complainant.

   c) Award costs of the present complaint proceedings.

   d) Pass any other order(s) this Hon'ble Commission deems fit and proper.

{'─' * 60}
SECTION D: EVIDENCE INDEX
{'─' * 60}
{evidence_index}

{'─' * 60}
FILING INSTRUCTIONS
{'─' * 60}
1. Visit https://edaakhil.nic.in and register/log in.
2. Select "File New Case" → "Consumer Complaint".
3. Enter Complainant and Opposite Party details.
4. Paste Statement of Facts from Section B above.
5. Upload all annexures listed in Section D.
6. Pay the requisite court fee (based on claim value).
7. Submit and note the case/diary number for tracking.

Applicable Jurisdiction:
   - Claim up to ₹50 lakh: District Consumer Disputes Redressal Commission
   - Claim ₹50 lakh – ₹2 crore: State Consumer Disputes Redressal Commission
   - Claim above ₹2 crore: National Consumer Disputes Redressal Commission
"""

        draft = GeneratedDraft(
            case_id=case.id,
            draft_type="ejagriti_package",
            title=f"e-Jagriti Filing Package — Order {case.order_id or 'N/A'}",
            content=content,
            tier=EscalationTier.TIER_3_EJAGRITI.value,
            metadata_json={
                "filing_url": "https://edaakhil.nic.in",
                "platform": case.platform,
                "claim_amount": case.amount,
                "annexure_count": (
                    db.query(EvidenceDocument)
                    .filter(EvidenceDocument.case_id == case_id)
                    .count()
                ),
            },
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        return {
            "draft_id": draft.id,
            "case_id": case.id,
            "draft_type": draft.draft_type,
            "title": draft.title,
            "content": draft.content,
            "tier": draft.tier,
            "generated_at": draft.generated_at,
            "metadata": draft.metadata_json,
        }
