"""Script to generate academic PDF matching the exact structure and visual style
of the reference paper for ConsumerAssist.
"""

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
import os

def generate_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=44,
        rightMargin=44,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=17,
        alignment=TA_CENTER,
        textColor=colors.black,
        spaceAfter=3
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12.5,
        alignment=TA_CENTER,
        textColor=colors.black,
        spaceAfter=7
    )

    authors_style = ParagraphStyle(
        'DocAuthors',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        alignment=TA_CENTER,
        textColor=colors.black,
        spaceAfter=9
    )

    abstract_heading_style = ParagraphStyle(
        'AbstractHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11.5,
        alignment=TA_LEFT,
        textColor=colors.black,
        spaceAfter=2
    )

    body_style = ParagraphStyle(
        'BodyJustified',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.7,
        leading=9.9,
        alignment=TA_JUSTIFY,
        textColor=colors.black,
        spaceAfter=5
    )

    sec_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11.5,
        alignment=TA_LEFT,
        textColor=colors.black,
        spaceBefore=3,
        spaceAfter=2
    )

    subsec_heading_style = ParagraphStyle(
        'SubSectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.2,
        leading=10.5,
        alignment=TA_LEFT,
        textColor=colors.black,
        spaceBefore=2,
        spaceAfter=1
    )

    story = []

    # Title
    story.append(Paragraph("CONSUMERASSIST: COMPUTATIONAL CASE-INTELLIGENCE & GRIEVANCE RESOLUTION AGENT", title_style))
    story.append(Paragraph("A Task-Oriented Dialogue, Statutory Evidence Grounding, and Multi-Tier Escalation Architecture for Indian E-Commerce", subtitle_style))

    # Authors
    story.append(Paragraph("UMUGASH — RA2212704010035<br/>PROJECT PARTNER — RA2212704010036", authors_style))

    # Abstract
    story.append(Paragraph("ABSTRACT", abstract_heading_style))
    abstract_text = (
        "The exponential expansion of digital commerce and quick-commerce in India has precipitated a surge in consumer disputes, "
        "characterized by delayed refunds, non-delivery, counterfeit goods, and algorithmic dark patterns. Existing grievance redressal "
        "mechanisms remain fragmented, leaving consumers to navigate convoluted customer care bots and complex legal portals without procedural guidance. "
        "This paper presents ConsumerAssist, an end-to-end computational case-intelligence and legal-tech conversational AI agent designed to assist "
        "consumers in resolving grievances against e-commerce platforms (Amazon, Flipkart, Zepto, Blinkit, Swiggy Instamart). The proposed system "
        "employs a 12-stage guided workflow spanning three statutory escalation tiers: Tier 1 (Platform Grievance Officer), Tier 2 (National Consumer "
        "Helpline - NCH 1915), and Tier 3 (e-Jagriti Consumer Commission e-filing). The core architecture couples a Dialogue State Tracking (DST) "
        "engine over eight critical grievance slots with multimodal document OCR field extraction, statutory evidence gap analysis, chronological "
        "timeline reconstruction with conflict detection, and deterministic legal document synthesis. Grounded strictly in the Consumer Protection "
        "Act 2019 and the Consumer Protection (E-Commerce) Rules 2020, ConsumerAssist acts as an interpretable procedural decision-support system, "
        "ensuring factual consistency and zero legal hallucination while democratizing access to pre-litigation and statutory dispute redressal."
    )
    story.append(Paragraph(abstract_text, body_style))

    # Keywords
    keywords_text = (
        "<b><i>Keywords</i>— Natural Language Processing, Legal-Tech AI, Task-Oriented Dialogue Systems, Dialogue State Tracking (DST), "
        "Consumer Protection Act 2019, Multimodal Document OCR, Automated Grievance Redressal, Explainable AI.</b>"
    )
    story.append(Paragraph(keywords_text, body_style))
    story.append(Spacer(1, 4))

    # Section I: Literature Survey
    story.append(Paragraph("I. LITERATURE SURVEY", sec_heading_style))

    # Subsections
    subsections = [
        (
            "A. Statutory Redressal Framework (CPA 2019 & E-Commerce Rules 2020)",
            "The Consumer Protection Act 2019 and the Consumer Protection (E-Commerce) Rules 2020 establish mandatory grievance redressal protocols "
            "for e-commerce entities in India, including the appointment of a resident Grievance Officer, 48-hour acknowledgment SLAs, and 30-day "
            "dispute disposal mandates. The National Consumer Helpline (NCH - 1915 / consumerhelpline.gov.in) and the e-Jagriti digital commission filing "
            "portal provide official pre-litigation and judicial dispute escalation pathways. In ConsumerAssist, this statutory architecture serves as the "
            "formal normative foundation for stage transitions, limitation compliance auditing (Section 69 two-year window), and procedural docket generation."
        ),
        (
            "B. Synthetic Indian E-Commerce Grievance Corpus",
            "Publicly available legal benchmarks rarely capture the informal, multilingual, and localized linguistic nuances of Indian online retail disputes. "
            "To support supervised intent identification and entity extraction, a specialized dataset of synthetic and anonymized Indian consumer complaints "
            "was developed. The corpus spans key grievance categories including refund denial, delivery default, damaged goods, hidden delivery surcharges, "
            "and perishable quick-commerce discrepancies, annotated with domain entities such as platform names, order identifiers, disputed sums, and transactional dates."
        ),
        (
            "C. Task-Oriented Dialogue & Dialogue State Tracking (DST)",
            "Classical dialogue systems rely on fixed decision trees, whereas modern deep task-oriented dialogue models (such as MultiWOZ benchmarks) "
            "track slot-value representations across conversational turns. In ConsumerAssist, the Dialogue State Tracker models eight essential case parameters "
            "(Platform, Order ID, Issue Category, Disputed Amount, Incident Date, Support Contacted, Evidence Status, and Remedy Sought). The dialogue manager "
            "combines zero-latency heuristic intent parsing with large language model semantic resolution to prevent repetitive prompting and handle conversational digressions."
        ),
        (
            "D. Multimodal Document OCR & Statutory Evidence Ingestion",
            "Automated dispute resolution requires verifiable documentary proof to substantiate user claims. Previous studies have demonstrated the efficacy "
            "of optical character recognition (OCR) and vision-language models in extracting key-value pairs from commercial receipts, tax invoices, and order "
            "confirmations. ConsumerAssist incorporates multimodal document processing to parse uploaded images and PDFs, computing a dynamic Case Readiness Score "
            "against statutory evidence requirements while automatically waiving inapplicable items (such as bank proofs for Cash on Delivery transactions)."
        ),
        (
            "E. Indian Legal NLP Benchmarks (LegalEval & InLegalBERT)",
            "Recent advances in legal language processing, including LegalEval, InLegalBERT, and Supreme Court judgment classification corpora, demonstrate "
            "that legal concepts exhibit distinct syntactic and semantic structures requiring domain adaptation. While existing models target legal text "
            "summarization and judicial citation prediction, they underscore the necessity of domain-specific semantic understanding when parsing statutory definitions, "
            "unfair trade practices (Section 2(47)), and consumer deficiency of service (Section 2(11))."
        ),
        (
            "F. Research Gap",
            "Existing legal NLP research predominantly emphasizes corporate contract risk analysis (CUAD, LEDGAR) or retrospective case-law outcome prediction. "
            "Consequently, an operational research gap persists in systems that bridge initial unstructured consumer intake with formal, multi-tier legal redressal. "
            "Prior implementations fail to integrate dynamic slot-filling, multimodal evidence verification, timeline anomaly detection, and automated "
            "procedural notice generation within a unified, interactive workflow. ConsumerAssist resolves this limitation by delivering a complete, "
            "statutorily grounded computational pipeline that empowers consumers from initial informal dispute to formal statutory adjudication."
        )
    ]

    for title, desc in subsections:
        story.append(Paragraph(title, subsec_heading_style))
        story.append(Paragraph(desc, body_style))

    doc.build(story)
    print(f"PDF successfully generated at: {output_path}")

if __name__ == "__main__":
    out_file = os.path.join(os.getcwd(), "ConsumerAssist_Project_Documentation.pdf")
    generate_pdf(out_file)
