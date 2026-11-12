import React from 'react';
import { SlotState } from '../types';
import { STAGES } from './WorkflowProgressBar';

interface DialogueStateSidebarProps {
  slots: SlotState;
  intentDetected?: string | null;
  confidence?: number | null;
  currentStage?: string;
}

const SLOT_CONFIG: Array<{ key: keyof SlotState; label: string; hint: string }> = [
  { key: 'platform', label: 'E-Commerce Platform', hint: 'Amazon, Flipkart, Zepto...' },
  { key: 'order_id', label: 'Order / Ref ID', hint: 'Unique order identifier' },
  { key: 'issue_category', label: 'Issue Category', hint: 'Classified grievance type' },
  { key: 'amount', label: 'Disputed Amount', hint: 'Transaction value in INR' },
  { key: 'incident_date', label: 'Incident Date', hint: 'Date of incident/delivery' },
  { key: 'customer_support_contacted', label: 'Support Contacted', hint: 'Prior attempt to resolve' },
  { key: 'evidence_uploaded', label: 'Evidence Uploaded', hint: 'Receipts/photos attached' },
  { key: 'resolution_sought', label: 'Relief / Remedy', hint: 'Full refund, replacement...' },
];

export const DialogueStateSidebar: React.FC<DialogueStateSidebarProps> = ({
  slots,
  intentDetected,
  confidence,
  currentStage = '1. Intake & Greeting',
}) => {
  const currentStageIndex = STAGES.findIndex((s) => s.toLowerCase() === currentStage.toLowerCase());
  const effectiveStageIndex = currentStageIndex === -1 ? 0 : currentStageIndex;

  const filledCount = SLOT_CONFIG.filter(({ key }) => {
    const val = slots[key];
    return val !== null && val !== undefined && val !== '' && val !== false;
  }).length;

  return (
    <div className="dst-tab-container">
      {/* DST Summary Card */}
      <div className="dst-header-card">
        <div className="dst-header-left">
          <h4>Dialogue State Tracking (DST)</h4>
          <span className="dst-sub">Slot-filling status for case record</span>
        </div>
        <div className="dst-progress-pill">
          <span>{filledCount} of 8 Filled</span>
        </div>
      </div>

      {/* Slots Grid */}
      <div className="slots-grid-list">
        {SLOT_CONFIG.map(({ key, label, hint }) => {
          const val = slots[key];
          let displayVal = 'Missing';
          let isFilled = false;

          if (val !== null && val !== undefined && val !== '') {
            isFilled = true;
            if (key === 'amount') displayVal = `₹${val}`;
            else if (typeof val === 'boolean') displayVal = val ? 'Yes' : 'No';
            else displayVal = String(val);
          }

          return (
            <div key={key} className={`slot-row-card ${isFilled ? 'slot-filled' : 'slot-unfilled'}`}>
              <div className="slot-row-header">
                <span className="slot-title">{label}</span>
                <span className={`slot-status-tag ${isFilled ? 'tag-filled' : 'tag-missing'}`}>
                  {isFilled ? '✓ Verified' : '✗ Missing'}
                </span>
              </div>
              <div className="slot-row-value">
                {isFilled ? displayVal : <span className="slot-placeholder">{hint}</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Intent & Confidence Meter */}
      {intentDetected && (
        <div className="intent-card-box">
          <div className="intent-header">
            <span>DETECTED COMPLAINT INTENT</span>
            {confidence && (
              <span className="confidence-percent">
                {(confidence * 100).toFixed(1)}% match
              </span>
            )}
          </div>
          <div className="intent-name">{intentDetected}</div>
          {confidence && (
            <div className="confidence-track">
              <div
                className="confidence-fill"
                style={{ width: `${Math.min(100, Math.max(15, confidence * 100))}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* Future Workflow Road Map */}
      <div className="future-steps-card">
        <div className="future-steps-header">
          <span>12-STAGE WORKFLOW ROADMAP</span>
        </div>
        <div className="steps-vertical-list">
          {STAGES.map((stg, i) => {
            const isPast = i < effectiveStageIndex;
            const isCurrent = i === effectiveStageIndex;
            const isFuture = i > effectiveStageIndex;

            return (
              <div
                key={i}
                className={`step-vertical-item ${isPast ? 'step-past' : ''} ${isCurrent ? 'step-current' : ''} ${isFuture ? 'step-future' : ''}`}
              >
                <div className="step-bullet">
                  {isPast ? '✓' : i + 1}
                </div>
                <div className="step-name-col">
                  <span className="step-label">{stg.replace(/^\d+\.\s*/, '')}</span>
                  {isCurrent && <span className="current-step-badge">Active Stage</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
