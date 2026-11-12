export interface SlotState {
  platform: string | null;
  order_id: string | null;
  issue_category: string | null;
  amount: number | null;
  incident_date: string | null;
  customer_support_contacted: boolean | null;
  evidence_uploaded: boolean;
  resolution_sought: string | null;
}

export interface ExtractedEntity {
  type: string;
  value: string;
  normalized?: string;
  normalized_value?: string;
  confidence?: number;
}

export interface DialogueTurn {
  id?: string;
  turn_number: number;
  role: 'user' | 'assistant';
  message: string;
  timestamp?: string;
  intent_detected?: string;
  confidence?: number;
}

export interface TimelineEvent {
  id: string;
  event_date: string;
  event_date_normalized?: string;
  event_type: string;
  description: string;
  source: string;
  has_conflict: boolean;
  conflict_details?: string;
}

export interface EvidenceDocument {
  id: string;
  filename: string;
  file_type: string;
  upload_timestamp?: string;
  processing_status: string;
  extracted_fields?: {
    vendor?: string;
    invoice_date?: string;
    items?: string[];
    tax?: string;
    total_amount?: string;
    order_id?: string;
  };
}

export interface CaseOverview {
  id: string;
  created_at: string;
  updated_at: string;
  status: string;
  workflow_stage: string;
  escalation_tier: string;
  platform?: string | null;
  order_id?: string | null;
  issue_category?: string | null;
  amount?: number | null;
  incident_date?: string | null;
  customer_support_contacted?: boolean | null;
  evidence_uploaded: boolean;
  resolution_sought?: string | null;
  case_readiness_score: number;
  evidence_gap_checklist?: Record<string, boolean>;
}

export interface CaseDetail extends CaseOverview {
  dialogue_turns: DialogueTurn[];
  timeline_events: TimelineEvent[];
  evidence_documents: EvidenceDocument[];
  escalation_history: Array<{
    id: string;
    from_tier: string;
    to_tier: string;
    from_stage: string;
    to_stage: string;
    reason?: string;
    timestamp?: string;
  }>;
  generated_drafts: Array<{
    id: string;
    draft_type: string;
    title: string;
    tier: string;
    generated_at?: string;
  }>;
}

export interface ChatResponse {
  case_id: string;
  turn_number: number;
  assistant_message: string;
  slots: SlotState;
  missing_slots: string[];
  intent_detected?: string;
  confidence?: number;
  workflow_stage: string;
  escalation_tier: string;
  entities_extracted: ExtractedEntity[];
}

export interface EvidenceGapResponse {
  case_id: string;
  issue_category?: string;
  required_evidence: string[];
  submitted_evidence: string[];
  missing_evidence: string[];
  readiness_score: number;
  checklist: Record<string, boolean>;
}

export interface DraftResponse {
  draft_id: string;
  case_id: string;
  draft_type: string;
  title: string;
  content: string;
  tier: string;
  generated_at: string;
  metadata?: any;
}

export interface EvaluationMetrics {
  nlp_pipeline: {
    classification_accuracy: number;
    classification_macro_f1: number;
    entity_precision: number;
    entity_recall: number;
    entity_f1: number;
    event_extraction_f1: number;
    timeline_ordering_accuracy: number;
  };
  dialogue_quality: {
    required_field_collection_rate: number;
    unnecessary_follow_up_questions_count: number;
    task_completion_rate: number;
    avg_dialogue_turns_to_draft: number;
  };
  retrieval_trust: {
    verified_source_retrieval_accuracy: number;
    unsupported_recommendation_rate: number;
    complaint_document_factual_consistency: number;
    legal_citation_grounding: number;
  };
  comparison: {
    structured_workflow: any;
    plain_llm_baseline: any;
  };
}

