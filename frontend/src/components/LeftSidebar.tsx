import React, { useState } from 'react';
import { CaseOverview } from '../types';
import { AuthUser } from '../supabaseClient';

interface LeftSidebarProps {
  cases: CaseOverview[];
  activeCaseId: string | null;
  onSelectCase: (id: string) => void;
  onNewCase: () => void;
  onDeleteCase: (id: string) => void;
  user: AuthUser | null;
  onLogout: () => void;
  onOpenAuth: () => void;
}

export const LeftSidebar: React.FC<LeftSidebarProps> = ({
  cases,
  activeCaseId,
  onSelectCase,
  onNewCase,
  onDeleteCase,
  user,
  onLogout,
  onOpenAuth,
}) => {
  const [caseToDelete, setCaseToDelete] = useState<CaseOverview | null>(null);

  const handleDeleteClick = (e: React.MouseEvent, c: CaseOverview) => {
    e.stopPropagation();
    setCaseToDelete(c);
  };

  const confirmDelete = () => {
    if (caseToDelete) {
      onDeleteCase(caseToDelete.id);
      setCaseToDelete(null);
    }
  };

  return (
    <aside className="left-sidebar">
      {/* Brand Header */}
      <div className="sidebar-brand">
        <div className="brand-badge">⚖️</div>
        <div className="brand-text">
          <h2>ConsumerAssist</h2>
          <span>AI Case-Intelligence</span>
        </div>
      </div>

      {/* New Grievance Primary Action */}
      <div className="sidebar-action-wrap">
        <button className="new-grievance-primary-btn" onClick={onNewCase}>
          <span className="btn-icon">+</span>
          <span>New Grievance</span>
        </button>
      </div>

      {/* Case History Section */}
      <div className="sidebar-history-section">
        <div className="history-header">
          <span>PAST GRIEVANCES ({cases.length})</span>
        </div>

        <div className="history-list">
          {cases.length === 0 ? (
            <div className="empty-history-notice">
              <p>No past cases recorded.</p>
              <span>Click "New Grievance" above to start drafting a complaint.</span>
            </div>
          ) : (
            cases.map((c) => {
              const isActive = c.id === activeCaseId;
              const dateStr = c.created_at
                ? new Date(c.created_at).toLocaleDateString('en-IN', {
                    month: 'short',
                    day: 'numeric',
                  })
                : '';

              return (
                <div
                  key={c.id}
                  className={`history-card ${isActive ? 'active' : ''}`}
                  onClick={() => onSelectCase(c.id)}
                >
                  <div className="history-card-top">
                    <span className={`platform-pill ${c.platform || 'General'}`}>
                      {c.platform || 'General'}
                    </span>
                    <div className="card-top-right">
                      <span className="history-card-date">{dateStr}</span>
                      <button
                        className="delete-case-btn"
                        title="Delete grievance"
                        onClick={(e) => handleDeleteClick(e, c)}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  <div className="history-card-title">
                    {c.issue_category || 'Consumer Complaint'}
                  </div>

                  <div className="history-card-footer">
                    <span className="history-card-stage">
                      {c.workflow_stage?.replace(/^\d+\.\s*/, '') || 'Intake'}
                    </span>
                    {c.amount ? (
                      <span className="history-card-amount">₹{c.amount}</span>
                    ) : null}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* User Profile Footer */}
      <div className="sidebar-user-footer">
        {user ? (
          <div className="user-profile-bar">
            <div className="user-avatar-circle">
              {user.name ? user.name.charAt(0).toUpperCase() : 'G'}
            </div>
            <div className="user-info-text">
              <span className="user-display-name">{user.name}</span>
              <span className="user-display-email" title={user.email}>{user.email}</span>
            </div>
            <button className="user-logout-btn" title="Sign out" onClick={onLogout}>
              ⎋
            </button>
          </div>
        ) : (
          <button className="user-login-prompt-btn" onClick={onOpenAuth}>
            <span>Sign in with Google</span>
          </button>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {caseToDelete && (
        <div className="confirm-delete-overlay">
          <div className="confirm-delete-dialog">
            <div className="dialog-icon">⚠️</div>
            <h3>Remove Grievance Record?</h3>
            <p>
              Are you sure you want to remove current case (
              <strong>{caseToDelete.platform || 'Platform'} — {caseToDelete.issue_category || 'Complaint'}</strong>
              ) from ConsumerAssist? All associated dialogue turns, evidence, and generated drafts will be permanently deleted.
            </p>
            <div className="dialog-actions">
              <button
                className="btn-dialog-cancel"
                onClick={() => setCaseToDelete(null)}
              >
                No, Keep Case
              </button>
              <button
                className="btn-dialog-delete"
                onClick={confirmDelete}
              >
                Yes, Remove Case
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
