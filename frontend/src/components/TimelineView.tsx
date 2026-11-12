import React from 'react';
import { TimelineEvent } from '../types';

interface TimelineViewProps {
  events: TimelineEvent[];
  conflicts: any[];
}

export const TimelineView: React.FC<TimelineViewProps> = ({ events, conflicts }) => {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#1e293b' }}>
          Chronological Event History & Audit Trail
        </h3>
        {conflicts.length > 0 && (
          <span style={{ color: '#ef4444', fontWeight: 600, fontSize: '0.85rem' }}>
            ⚠️ {conflicts.length} Conflict(s) Detected
          </span>
        )}
      </div>

      {events.length === 0 ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: '30px 0' }}>
          No timeline events reconstructed yet. Speak with the assistant or upload documents.
        </div>
      ) : (
        <div className="timeline-list">
          {events.map((evt) => (
            <div
              key={evt.id}
              className={`timeline-item ${evt.has_conflict ? 'conflict' : ''}`}
            >
              <div className="timeline-dot" />
              <div className="timeline-card">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="timeline-date">{evt.event_date}</span>
                  <span style={{ fontSize: '0.72rem', background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>
                    Source: {evt.source}
                  </span>
                </div>
                <div className="timeline-desc">{evt.description}</div>
                {evt.has_conflict && evt.conflict_details && (
                  <div className="conflict-alert">
                    <strong>Discrepancy:</strong> {evt.conflict_details}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

