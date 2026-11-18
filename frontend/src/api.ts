import {
  ChatResponse,
  CaseOverview,
  CaseDetail,
  TimelineEvent,
  EvidenceGapResponse,
  DraftResponse,
  EvaluationMetrics,
} from './types';
import { getAccessToken } from './supabaseClient';

const API_BASE = '/api';

// Wraps fetch with the signed-in user's bearer token; the backend derives identity from it.
async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res;
}

export async function sendMessage(
  caseId: string | null,
  message: string,
  user?: { id?: string; email?: string } | null
): Promise<ChatResponse> {
  const res = await apiFetch(`${API_BASE}/chat/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      message,
    }),
  });
  return res.json();
}

export async function listCases(user?: { id?: string; email?: string } | null): Promise<CaseOverview[]> {
  void user; // identity comes from the bearer token
  const res = await apiFetch(`${API_BASE}/cases/`);
  return res.json();
}

export async function deleteCase(caseId: string): Promise<{ status: string; case_id: string; message: string }> {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}`, {
    method: 'DELETE',
  });
  return res.json();
}

export async function getCaseDetail(caseId: string): Promise<CaseDetail> {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}`);
  return res.json();
}

export async function getCaseTimeline(caseId: string): Promise<{ case_id: string; events: TimelineEvent[]; conflicts: any[] }> {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}/timeline`);
  return res.json();
}

export async function getEvidenceGaps(caseId: string): Promise<EvidenceGapResponse> {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}/evidence-gaps`);
  return res.json();
}

export async function escalateCase(caseId: string, action: string = 'advance', targetStage?: string) {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}/escalate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, action, target_stage: targetStage }),
  });
  return res.json();
}

export async function generateDraft(caseId: string, draftType: string): Promise<DraftResponse> {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}/generate-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, draft_type: draftType }),
  });
  return res.json();
}

export async function listDrafts(caseId: string): Promise<DraftResponse[]> {
  const res = await apiFetch(`${API_BASE}/cases/${caseId}/drafts`);
  return res.json();
}

export async function uploadEvidenceDocument(caseId: string, file: File) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiFetch(`${API_BASE}/documents/upload/${caseId}`, {
    method: 'POST',
    body: formData,
  });
  return res.json();
}

export async function getEvaluationMetrics(): Promise<EvaluationMetrics> {
  const res = await apiFetch(`${API_BASE}/evaluation/metrics`);
  return res.json();
}

