# CONSUMERASSIST: COMPUTATIONAL CASE-INTELLIGENCE & GRIEVANCE RESOLUTION AGENT
### A Task-Oriented Dialogue, Statutory Evidence Grounding, and Multi-Tier Escalation Architecture for Indian E-Commerce

**UMUGASH — RA2212704010035**  
**PROJECT PARTNER — RA2212704010036**  

---

### ABSTRACT
The exponential expansion of digital commerce and quick-commerce in India has precipitated a surge in consumer disputes, characterized by delayed refunds, non-delivery, counterfeit goods, and algorithmic dark patterns. Existing grievance redressal mechanisms remain fragmented, leaving consumers to navigate convoluted customer care bots and complex legal portals without procedural guidance. This paper presents **ConsumerAssist**, an end-to-end computational case-intelligence and legal-tech conversational AI agent designed to assist consumers in resolving grievances against e-commerce platforms (Amazon, Flipkart, Zepto, Blinkit, Swiggy Instamart). The proposed system employs a 12-stage guided workflow spanning three statutory escalation tiers: Tier 1 (Platform Grievance Officer), Tier 2 (National Consumer Helpline - NCH 1915), and Tier 3 (e-Jagriti Consumer Commission e-filing). The core architecture couples a Dialogue State Tracking (DST) engine over eight critical grievance slots with multimodal document OCR field extraction, statutory evidence gap analysis, chronological timeline reconstruction with conflict detection, and deterministic legal document synthesis. Grounded strictly in the Consumer Protection Act 2019 and the Consumer Protection (E-Commerce) Rules 2020, ConsumerAssist acts as an interpretable procedural decision-support system, ensuring factual consistency and zero legal hallucination while democratizing access to pre-litigation and statutory dispute redressal.

**Keywords—** Natural Language Processing, Legal-Tech AI, Task-Oriented Dialogue Systems, Dialogue State Tracking (DST), Consumer Protection Act 2019, Multimodal Document OCR, Automated Grievance Redressal, Explainable AI.

---

### I. LITERATURE SURVEY

#### A. Statutory Redressal Framework (CPA 2019 & E-Commerce Rules 2020)
The Consumer Protection Act 2019 and the Consumer Protection (E-Commerce) Rules 2020 establish mandatory grievance redressal protocols for e-commerce entities in India, including the appointment of a resident Grievance Officer, 48-hour acknowledgment SLAs, and 30-day dispute disposal mandates. The National Consumer Helpline (NCH - 1915 / consumerhelpline.gov.in) and the e-Jagriti digital commission filing portal provide official pre-litigation and judicial dispute escalation pathways. In ConsumerAssist, this statutory architecture serves as the formal normative foundation for stage transitions, limitation compliance auditing (Section 69 two-year window), and procedural docket generation.

#### B. Synthetic Indian E-Commerce Grievance Corpus
Publicly available legal benchmarks rarely capture the informal, multilingual, and localized linguistic nuances of Indian online retail disputes. To support supervised intent identification and entity extraction, a specialized dataset of synthetic and anonymized Indian consumer complaints was developed. The corpus spans key grievance categories including refund denial, delivery default, damaged goods, hidden delivery surcharges, and perishable quick-commerce discrepancies, annotated with domain entities such as platform names, order identifiers, disputed sums, and transactional dates.

#### C. Task-Oriented Dialogue & Dialogue State Tracking (DST)
Classical dialogue systems rely on fixed decision trees, whereas modern deep task-oriented dialogue models (such as MultiWOZ benchmarks) track slot-value representations across conversational turns. In ConsumerAssist, the Dialogue State Tracker models eight essential case parameters (Platform, Order ID, Issue Category, Disputed Amount, Incident Date, Support Contacted, Evidence Status, and Remedy Sought). The dialogue manager combines zero-latency heuristic intent parsing with large language model semantic resolution to prevent repetitive prompting and handle conversational digressions.

#### D. Multimodal Document OCR & Statutory Evidence Ingestion
Automated dispute resolution requires verifiable documentary proof to substantiate user claims. Previous studies have demonstrated the efficacy of optical character recognition (OCR) and vision-language models in extracting key-value pairs from commercial receipts, tax invoices, and order confirmations. ConsumerAssist incorporates multimodal document processing to parse uploaded images and PDFs, computing a dynamic Case Readiness Score against statutory evidence requirements while automatically waiving inapplicable items (such as bank proofs for Cash on Delivery transactions).

#### E. Indian Legal NLP Benchmarks (LegalEval & InLegalBERT)
Recent advances in legal language processing, including LegalEval, InLegalBERT, and Supreme Court judgment classification corpora, demonstrate that legal concepts exhibit distinct syntactic and semantic structures requiring domain adaptation. While existing models target legal text summarization and judicial citation prediction, they underscore the necessity of domain-specific semantic understanding when parsing statutory definitions, unfair trade practices (Section 2(47)), and consumer deficiency of service (Section 2(11)).

#### F. Research Gap
Existing legal NLP research predominantly emphasizes corporate contract risk analysis (CUAD, LEDGAR) or retrospective case-law outcome prediction. Consequently, an operational research gap persists in systems that bridge initial unstructured consumer intake with formal, multi-tier legal redressal. Prior implementations fail to integrate dynamic slot-filling, multimodal evidence verification, timeline anomaly detection, and automated procedural notice generation within a unified, interactive workflow. ConsumerAssist resolves this limitation by delivering a complete, statutorily grounded computational pipeline that empowers consumers from initial informal dispute to formal statutory adjudication.

