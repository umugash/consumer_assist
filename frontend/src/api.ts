import {
  ChatResponse,
  CaseOverview,
  CaseDetail,
  TimelineEvent,
  EvidenceGapResponse,
  DraftResponse,
  EvaluationMetrics,
} from './types';

const API_BASE = '/api';

export async function sendMessage(
  caseId: string | null,
  message: string,
  user?: { id?: string; email?: string } | null
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      message,
      user_id: user?.id,
      user_email: user?.email,
    }),
  });
  if (!res.ok) throw new Error(`Chat error: ${res.statusText}`);
  return res.json();
}

export async function listCases(user?: { id?: string; email?: string } | null): Promise<CaseOverview[]> {
  const params = new URLSearchParams();
  if (user?.id) params.append('user_id', user.id);
  if (user?.email) params.append('user_email', user.email);

  const url = `${API_BASE}/cases/${params.toString() ? `?${params.toString()}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`List cases error: ${res.statusText}`);
  return res.json();
}

export async function deleteCase(caseId: string): Promise<{ status: string; case_id: string; message: string }> {
  const res = await fetch(`${API_BASE}/cases/${caseId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Delete case error: ${res.statusText}`);
  return res.json();
}

export async function getCaseDetail(caseId: string): Promise<CaseDetail> {
  const res = await fetch(`${API_BASE}/cases/${caseId}`);
  if (!res.ok) throw new Error(`Get case error: ${res.statusText}`);
  return res.json();
}

export async function getCaseTimeline(caseId: string): Promise<{ case_id: string; events: TimelineEvent[]; conflicts: any[] }> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/timeline`);
  if (!res.ok) throw new Error(`Timeline error: ${res.statusText}`);
  return res.json();
}

export async function getEvidenceGaps(caseId: string): Promise<EvidenceGapResponse> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/evidence-gaps`);
  if (!res.ok) throw new Error(`Evidence gap error: ${res.statusText}`);
  return res.json();
}

export async function escalateCase(caseId: string, action: string = 'advance', targetStage?: string) {
  const res = await fetch(`${API_BASE}/cases/${caseId}/escalate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, action, target_stage: targetStage }),
  });
  if (!res.ok) throw new Error(`Escalate error: ${res.statusText}`);
  return res.json();
}

export async function generateDraft(caseId: string, draftType: string): Promise<DraftResponse> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/generate-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, draft_type: draftType }),
  });
  if (!res.ok) throw new Error(`Generate draft error: ${res.statusText}`);
  return res.json();
}

export async function listDrafts(caseId: string): Promise<DraftResponse[]> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/drafts`);
  if (!res.ok) throw new Error(`List drafts error: ${res.statusText}`);
  return res.json();
}

export async function uploadEvidenceDocument(caseId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/documents/upload/${caseId}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload error: ${res.statusText}`);
  return res.json();
}

export async function getEvaluationMetrics(): Promise<EvaluationMetrics> {
  const res = await fetch(`${API_BASE}/evaluation/metrics`);
  if (!res.ok) throw new Error(`Metrics error: ${res.statusText}`);
  return res.json();
}

