import React, { useState } from 'react';
import { DraftResponse } from '../types';

interface DraftPanelProps {
  onGenerateDraft: (draftType: string) => void;
  currentDraft: DraftResponse | null;
  draftsList: DraftResponse[];
  loading: boolean;
}

export const DraftPanel: React.FC<DraftPanelProps> = ({
  onGenerateDraft,
  currentDraft,
  draftsList,
  loading,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (currentDraft?.content) {
      navigator.clipboard.writeText(currentDraft.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div>
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#1e293b', marginBottom: 14 }}>
        Statutory Draft Generator (Zero Hallucination Grounding)
      </h3>

      <div className="draft-actions">
        <button
          className="draft-btn"
          onClick={() => onGenerateDraft('platform_email')}
          disabled={loading}
        >
          📧 Tier 1: Platform Escalation
        </button>
        <button
          className="draft-btn"
          style={{ background: '#d97706' }}
          onClick={() => onGenerateDraft('nch_summary')}
          disabled={loading}
        >
          🏛️ Tier 2: NCH Docket
        </button>
        <button
          className="draft-btn"
          style={{ background: '#dc2626' }}
          onClick={() => onGenerateDraft('ejagriti_package')}
          disabled={loading}
        >
          ⚖️ Tier 3: e-Jagriti Package
        </button>
      </div>

      {currentDraft ? (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#1e293b' }}>
              {currentDraft.title}
            </span>
            <button className="copy-btn" onClick={handleCopy}>
              {copied ? '✓ Copied to Clipboard' : 'Copy Draft'}
            </button>
          </div>
          <div className="draft-preview">{currentDraft.content}</div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: '40px 0' }}>
          Select a tier button above to generate a grounded legal or administrative escalation draft.
        </div>
      )}
    </div>
  );
};

