import React from 'react';

interface WorkflowProgressBarProps {
  currentStage: string;
  currentTier: string;
  onAdvance: () => void;
  loading: boolean;
}

export const STAGES = [
  '1. Intake & Greeting',
  '2. Issue Classification',
  '3. Slot Filling',
  '4. Evidence Ingestion & OCR',
  '5. Timeline Reconstruction',
  '6. Conflict & Gap Verification',
  '7. Tier 1: Platform Grievance Routing & Draft',
  '8. Platform SLA/Response Tracking',
  '9. Tier 2: NCH Readiness',
  '10. NCH Docket Generation',
  '11. Tier 3: e-Jagriti Pre-Filing Checklist',
  '12. Final Consumer Commission Filing Package',
];

export const WorkflowProgressBar: React.FC<WorkflowProgressBarProps> = ({
  currentStage,
  currentTier,
  onAdvance,
  loading,
}) => {
  const currentIndex = STAGES.findIndex((s) => s.toLowerCase() === currentStage.toLowerCase());
  const effectiveIndex = currentIndex === -1 ? 0 : currentIndex;

  const tierClass = currentTier.includes('Tier 3')
    ? 'Tier3'
    : currentTier.includes('Tier 2')
    ? 'Tier2'
    : 'Tier1';

  const cleanStageName = currentStage.replace(/^\d+\.\s*/, '');
  const nextStage = effectiveIndex < STAGES.length - 1 ? STAGES[effectiveIndex + 1].replace(/^\d+\.\s*/, '') : null;

  return (
    <div className="stepper-header-panel">
      <div className="stepper-top-row">
        <div className="stepper-tier-info">
          <span className={`stepper-tier-pill ${tierClass}`}>
            {currentTier.split(':')[0]}
          </span>
          <div className="stepper-stage-title">
            <span className="stage-index-text">Stage {effectiveIndex + 1} of 12:</span>
            <span className="stage-name-text">{cleanStageName}</span>
          </div>
        </div>

        <button
          className="advance-stage-action-btn"
          onClick={onAdvance}
          disabled={loading || effectiveIndex >= STAGES.length - 1}
          title={nextStage ? `Advance to: ${nextStage}` : 'All stages complete'}
        >
          <span>Advance Stage</span>
          <span className="btn-arrow">→</span>
        </button>
      </div>

      {/* Visual Compact Step Indicator */}
      <div className="stepper-track-bar">
        {STAGES.map((stg, idx) => {
          const isDone = idx < effectiveIndex;
          const isCurrent = idx === effectiveIndex;

          return (
            <div
              key={idx}
              className={`stepper-segment ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`}
              title={`${idx + 1}. ${stg.replace(/^\d+\.\s*/, '')}`}
            >
              <div className="segment-indicator">
                {isDone ? '✓' : idx + 1}
              </div>
            </div>
          );
        })}
      </div>

      {/* Next Step Guidance Text */}
      <div className="stepper-guidance-bar">
        {nextStage ? (
          <span className="guidance-next">
            <strong>Next Step:</strong> {nextStage}
          </span>
        ) : (
          <span className="guidance-complete">
            ✓ Final Consumer Commission Package Ready for Filing
          </span>
        )}
      </div>
    </div>
  );
};
