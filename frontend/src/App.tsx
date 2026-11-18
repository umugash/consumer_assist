import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ChatResponse,
  CaseOverview,
  CaseDetail,
  TimelineEvent,
  EvidenceGapResponse,
  DraftResponse,
  EvaluationMetrics,
  ExtractedEntity,
} from './types';
import * as api from './api';
import {
  AuthUser,
  getStoredUser,
  signOutUser,
  supabase,
  setStoredUser,
} from './supabaseClient';

import { LeftSidebar } from './components/LeftSidebar';
import { ChatPanel } from './components/ChatPanel';
import { WorkflowProgressBar } from './components/WorkflowProgressBar';
import { DialogueStateSidebar } from './components/DialogueStateSidebar';
import { TimelineView } from './components/TimelineView';
import { EvidenceManager } from './components/EvidenceManager';
import { DraftPanel } from './components/DraftPanel';
import { EvaluationDashboard } from './components/EvaluationDashboard';
import { AuthModal } from './components/AuthModal';

import './styles/global.css';

export const App: React.FC = () => {
  const [user, setUser] = useState<AuthUser | null>(() => (supabase ? getStoredUser() : null));
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  const [cases, setCases] = useState<CaseOverview[]>([]);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [timelineConflicts, setTimelineConflicts] = useState<any[]>([]);
  const [gapData, setGapData] = useState<EvidenceGapResponse | null>(null);
  const [draftsList, setDraftsList] = useState<DraftResponse[]>([]);
  const [currentDraft, setCurrentDraft] = useState<DraftResponse | null>(null);
  const [evaluationMetrics, setEvaluationMetrics] = useState<EvaluationMetrics | null>(null);
  const [latestEntities, setLatestEntities] = useState<ExtractedEntity[]>([]);

  const [activeTab, setActiveTab] = useState<'dst' | 'evidence' | 'timeline' | 'drafts' | 'evaluation'>('dst');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  // Resizable right drawer state (default 360px, min 280px, max 600px)
  const [drawerWidth, setDrawerWidth] = useState<number>(360);
  const isDraggingRef = useRef(false);

  // Handle horizontal mouse dragging to resize the right intelligence panel
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      // Right drawer width is window.innerWidth - moveEvent.clientX
      const newWidth = window.innerWidth - moveEvent.clientX;
      if (newWidth >= 260 && newWidth <= 650) {
        setDrawerWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, []);

  // Check Supabase session on mount (if OAuth redirected back)
  useEffect(() => {
    if (supabase) {
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user) {
          const authUser: AuthUser = {
            id: session.user.id,
            email: session.user.email || '',
            name: session.user.user_metadata?.full_name || session.user.email?.split('@')[0] || 'User',
            avatar_url: session.user.user_metadata?.avatar_url,
            isDemo: false,
          };
          setUser(authUser);
          setStoredUser(authUser);
        } else {
          setUser(null);
          setStoredUser(null);
        }
      });

      const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
        if (session?.user) {
          const authUser: AuthUser = {
            id: session.user.id,
            email: session.user.email || '',
            name: session.user.user_metadata?.full_name || session.user.email?.split('@')[0] || 'User',
            avatar_url: session.user.user_metadata?.avatar_url,
            isDemo: false,
          };
          setUser(authUser);
          setStoredUser(authUser);
        } else {
          setUser(null);
          setStoredUser(null);
        }
      });

      return () => subscription.unsubscribe();
    }
  }, []);

  // Reload user cases whenever user changes
  useEffect(() => {
    if (user) {
      loadCases();
      loadMetrics();
    } else {
      setCases([]);
      setActiveCaseId(null);
      setCaseDetail(null);
      setTimelineEvents([]);
      setTimelineConflicts([]);
      setGapData(null);
      setCurrentDraft(null);
      setDraftsList([]);
      setLatestEntities([]);
    }
  }, [user]);

  // Load details whenever activeCaseId changes
  useEffect(() => {
    if (activeCaseId) {
      loadCaseData(activeCaseId);
    }
  }, [activeCaseId]);

  const loadCases = async () => {
    try {
      const data = await api.listCases(user);
      setCases(data);
      if (data.length > 0 && !activeCaseId) {
        setActiveCaseId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load cases:', err);
    }
  };

  const loadCaseData = async (cid: string) => {
    try {
      const [detailRes, tlRes, gapsRes, draftsRes] = await Promise.allSettled([
        api.getCaseDetail(cid),
        api.getCaseTimeline(cid),
        api.getEvidenceGaps(cid),
        api.listDrafts(cid),
      ]);
      if (detailRes.status === 'fulfilled') {
        setCaseDetail(detailRes.value);
      }
      if (tlRes.status === 'fulfilled') {
        setTimelineEvents(tlRes.value.events || []);
        setTimelineConflicts(tlRes.value.conflicts || []);
      }
      if (gapsRes.status === 'fulfilled') {
        setGapData(gapsRes.value);
      }
      if (draftsRes.status === 'fulfilled') {
        setDraftsList(draftsRes.value);
        if (draftsRes.value.length > 0 && !currentDraft) {
          setCurrentDraft(draftsRes.value[0]);
        }
      }
    } catch (err) {
      console.error('Failed to load case data:', err);
    }
  };

  const loadMetrics = async () => {
    try {
      const metrics = await api.getEvaluationMetrics();
      setEvaluationMetrics(metrics);
    } catch (err) {
      console.error('Failed to load metrics:', err);
    }
  };

  // Auth Guard helper: trigger login modal if unauthenticated
  const requireAuth = (): boolean => {
    if (!user) {
      setIsAuthModalOpen(true);
      return false;
    }
    return true;
  };

  const handleSendMessage = async (msg: string): Promise<boolean> => {
    if (!requireAuth()) return false;
    setLoading(true);
    setChatError(null);
    try {
      const res: ChatResponse = await api.sendMessage(activeCaseId, msg, user);
      setLatestEntities(res.entities_extracted || []);

      if (!activeCaseId || activeCaseId !== res.case_id) {
        setActiveCaseId(res.case_id);
        await loadCases();
      } else {
        await loadCaseData(res.case_id);
      }
      return true;
    } catch (err: any) {
      console.error('Chat error:', err);
      setChatError(err.message || 'Message failed to send. Please check your connection or try again.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const handleNewCase = () => {
    if (!requireAuth()) return;
    setActiveCaseId(null);
    setCaseDetail(null);
    setTimelineEvents([]);
    setTimelineConflicts([]);
    setGapData(null);
    setCurrentDraft(null);
    setDraftsList([]);
    setLatestEntities([]);
  };

  const handleDeleteCase = async (caseId: string) => {
    try {
      await api.deleteCase(caseId);
      // If we just deleted the active case, clear selection or pick next
      if (activeCaseId === caseId) {
        const remaining = cases.filter((c) => c.id !== caseId);
        if (remaining.length > 0) {
          setActiveCaseId(remaining[0].id);
        } else {
          handleNewCase();
        }
      }
      await loadCases();
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  const handleAdvanceStage = async () => {
    if (!requireAuth()) return;
    if (!activeCaseId) return;
    setLoading(true);
    try {
      await api.escalateCase(activeCaseId, 'advance');
      await loadCaseData(activeCaseId);
    } catch (err) {
      console.error('Advance error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateDraft = async (draftType: string) => {
    if (!requireAuth()) return;
    if (!activeCaseId) return;
    setLoading(true);
    try {
      const draft = await api.generateDraft(activeCaseId, draftType);
      setCurrentDraft(draft);
      const drafts = await api.listDrafts(activeCaseId);
      setDraftsList(drafts);
      setActiveTab('drafts');
    } catch (err) {
      console.error('Generate draft error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadEvidence = async (file: File) => {
    if (!requireAuth()) return;
    if (!activeCaseId) return;
    setUploading(true);
    try {
      await api.uploadEvidenceDocument(activeCaseId, file);
      await loadCaseData(activeCaseId);
    } catch (err) {
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleAuthSuccess = (authenticatedUser: AuthUser) => {
    setUser(authenticatedUser);
    setIsAuthModalOpen(false);
  };

  const handleLogout = async () => {
    await signOutUser();
    setUser(null);
    setCases([]);
    setActiveCaseId(null);
    setCaseDetail(null);
    setTimelineEvents([]);
    setTimelineConflicts([]);
    setGapData(null);
    setCurrentDraft(null);
    setDraftsList([]);
    setLatestEntities([]);
  };

  const activeSlots = caseDetail
    ? {
        platform: caseDetail.platform || null,
        order_id: caseDetail.order_id || null,
        issue_category: caseDetail.issue_category || null,
        amount: caseDetail.amount || null,
        incident_date: caseDetail.incident_date || null,
        customer_support_contacted: caseDetail.customer_support_contacted ?? null,
        evidence_uploaded: caseDetail.evidence_uploaded,
        resolution_sought: caseDetail.resolution_sought || null,
      }
    : {
        platform: null,
        order_id: null,
        issue_category: null,
        amount: null,
        incident_date: null,
        customer_support_contacted: null,
        evidence_uploaded: false,
        resolution_sought: null,
      };

  return (
    <div className="app-root-layout">
      {/* Top Global Notice / Disclaimer */}
      <header className="app-global-banner">
        <div className="banner-left">
          <span className="banner-badge">⚖️ LEGAL-TECH AUDIT SYSTEM</span>
          <span className="banner-disclaimer">
            <strong>Disclaimer:</strong> Procedural information and drafting assistance — not personalized legal advice or a guaranteed outcome.
          </span>
        </div>
        <div className="banner-right">
          {user ? (
            <span className="user-active-badge">
              ● Logged in as: <strong>{user.email}</strong>
            </span>
          ) : (
            <button className="banner-login-btn" onClick={() => setIsAuthModalOpen(true)}>
              Sign in with Google
            </button>
          )}
        </div>
      </header>

      {/* Main 3-Section Unified Workspace with Dynamic Grid Columns */}
      <div
        className="app-main-workspace"
        style={{
          gridTemplateColumns: `var(--sidebar-w) 1fr 6px ${drawerWidth}px`,
        }}
      >
        {/* Section 1: Left Navigation Sidebar */}
        <LeftSidebar
          cases={cases}
          activeCaseId={activeCaseId}
          onSelectCase={(id) => setActiveCaseId(id)}
          onNewCase={handleNewCase}
          onDeleteCase={handleDeleteCase}
          user={user}
          onLogout={handleLogout}
          onOpenAuth={() => setIsAuthModalOpen(true)}
        />

        {/* Section 2: Center Primary Chat Workspace */}
        <main className="center-chat-workspace">
          <ChatPanel
            turns={caseDetail?.dialogue_turns || []}
            onSendMessage={handleSendMessage}
            onUploadEvidence={handleUploadEvidence}
            onSkipEvidence={() => handleSendMessage('skip')}
            latestEntities={latestEntities}
            loading={loading}
            uploading={uploading}
            workflowStage={caseDetail?.workflow_stage}
            activeCaseCategory={caseDetail?.issue_category}
            activeCasePlatform={caseDetail?.platform}
            errorMessage={chatError}
            onClearError={() => setChatError(null)}
          />
        </main>

        {/* Resizable Divider Handle */}
        <div
          className="workspace-resize-handle"
          onMouseDown={handleMouseDown}
          title="Drag to resize Case Intelligence panel"
        >
          <div className="resize-handle-bar" />
        </div>

        {/* Section 3: Right Tabbed Case Intelligence Panel */}
        <aside className="right-intelligence-drawer" style={{ width: `${drawerWidth}px` }}>
          {/* Top Stage & Tier Stepper */}
          <WorkflowProgressBar
            currentStage={caseDetail?.workflow_stage || '1. Intake & Greeting'}
            currentTier={caseDetail?.escalation_tier || 'Tier 1: Platform Escalation'}
            onAdvance={handleAdvanceStage}
            loading={loading}
          />

          {/* Tab Navigation Headers */}
          <div className="intelligence-tabs-nav">
            <button
              className={`intel-tab-btn ${activeTab === 'dst' ? 'active' : ''}`}
              onClick={() => setActiveTab('dst')}
            >
              <span>📋 State</span>
            </button>
            <button
              className={`intel-tab-btn ${activeTab === 'evidence' ? 'active' : ''}`}
              onClick={() => setActiveTab('evidence')}
            >
              <span>📑 Docs ({caseDetail?.evidence_documents?.length || 0})</span>
            </button>
            <button
              className={`intel-tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
              onClick={() => setActiveTab('timeline')}
            >
              <span>🕒 Time ({timelineEvents.length})</span>
            </button>
            <button
              className={`intel-tab-btn ${activeTab === 'drafts' ? 'active' : ''}`}
              onClick={() => setActiveTab('drafts')}
            >
              <span>📜 Drafts ({draftsList.length})</span>
            </button>
            <button
              className={`intel-tab-btn ${activeTab === 'evaluation' ? 'active' : ''}`}
              onClick={() => setActiveTab('evaluation')}
            >
              <span>📊 Metrics</span>
            </button>
          </div>

          {/* Active Tab Body */}
          <div className="intelligence-tab-body">
            {activeTab === 'dst' && (
              <DialogueStateSidebar
                slots={activeSlots}
                intentDetected={caseDetail?.issue_category || null}
                confidence={caseDetail?.dialogue_turns?.[0]?.confidence || null}
                currentStage={caseDetail?.workflow_stage || '1. Intake & Greeting'}
              />
            )}
            {activeTab === 'evidence' && (
              <EvidenceManager
                documents={caseDetail?.evidence_documents || []}
                gapData={gapData}
                onUpload={handleUploadEvidence}
                uploading={uploading}
              />
            )}
            {activeTab === 'timeline' && (
              <TimelineView events={timelineEvents} conflicts={timelineConflicts} />
            )}
            {activeTab === 'drafts' && (
              <DraftPanel
                onGenerateDraft={handleGenerateDraft}
                currentDraft={currentDraft}
                draftsList={draftsList}
                loading={loading}
              />
            )}
            {activeTab === 'evaluation' && (
              <EvaluationDashboard
                metrics={evaluationMetrics}
                onRefresh={loadMetrics}
                loading={loading}
              />
            )}
          </div>
        </aside>
      </div>

      {/* Google Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onSuccess={handleAuthSuccess}
        onClose={() => setIsAuthModalOpen(false)}
      />
    </div>
  );
};

export default App;
