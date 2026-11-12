import React, { useState } from 'react';
import { AuthUser, signInWithGoogleSupabase, isSupabaseConfigured, setStoredUser } from '../supabaseClient';

interface AuthModalProps {
  isOpen: boolean;
  onSuccess: (user: AuthUser) => void;
  onClose?: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onSuccess, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [customEmail, setCustomEmail] = useState('');

  if (!isOpen) return null;

  const handleRealGoogleOAuth = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      if (isSupabaseConfigured) {
        await signInWithGoogleSupabase();
      } else {
        setErrorMsg('Supabase credentials not configured in .env yet. Use the 1-Click Demo Google Account below for live demonstration.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'OAuth error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handleDemoGoogleSignIn = (emailChoice: string, nameChoice: string) => {
    const demoUser: AuthUser = {
      id: `google_${emailChoice.replace(/[^a-zA-Z0-9]/g, '_')}`,
      email: emailChoice,
      name: nameChoice,
      avatar_url: `https://api.dicebear.com/7.x/initials/svg?seed=${nameChoice}`,
      isDemo: true,
    };
    setStoredUser(demoUser);
    onSuccess(demoUser);
  };

  const handleCustomGoogleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customEmail.trim() || !customEmail.includes('@')) {
      setErrorMsg('Please enter a valid Google email address');
      return;
    }
    const namePart = customEmail.split('@')[0].replace(/[._]/g, ' ');
    const formattedName = namePart.charAt(0).toUpperCase() + namePart.slice(1);
    handleDemoGoogleSignIn(customEmail.trim().toLowerCase(), formattedName);
  };

  return (
    <div
      className="auth-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose();
      }}
    >
      <div className="auth-modal">
        {onClose && (
          <button
            type="button"
            className="auth-close-btn"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        )}
        <div className="auth-header">
          <div className="auth-logo">⚖️</div>
          <h2>Sign in to ConsumerAssist</h2>
          <p>Task-Oriented Consumer Grievance Resolution & Legal-Tech Agent</p>
        </div>

        {errorMsg && (
          <div className="auth-error-banner">
            ⚠️ {errorMsg}
          </div>
        )}

        <div className="auth-body">
          {/* Real Google OAuth Button (Supabase) */}
          <button
            className="google-btn primary-google-btn"
            onClick={handleRealGoogleOAuth}
            disabled={loading}
          >
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            <span>Continue with Google (Live Supabase Auth)</span>
          </button>

          <div className="auth-divider">
            <span>OR 1-CLICK DEMO GOOGLE ACCOUNT</span>
          </div>

          {/* Quick 1-Click Demo Google Accounts for Immediate Evaluation */}
          <div className="demo-accounts-list">
            <button
              type="button"
              className="demo-account-chip"
              onClick={() => handleDemoGoogleSignIn('rahul.verma@gmail.com', 'Rahul Verma')}
            >
              <div className="demo-avatar">RV</div>
              <div className="demo-details">
                <span className="demo-name">Rahul Verma</span>
                <span className="demo-email">rahul.verma@gmail.com (Zepto / Blinkit user)</span>
              </div>
              <span className="demo-arrow">→</span>
            </button>

            <button
              type="button"
              className="demo-account-chip"
              onClick={() => handleDemoGoogleSignIn('ananya.sharma@gmail.com', 'Ananya Sharma')}
            >
              <div className="demo-avatar">AS</div>
              <div className="demo-details">
                <span className="demo-name">Ananya Sharma</span>
                <span className="demo-email">ananya.sharma@gmail.com (Amazon / Flipkart user)</span>
              </div>
              <span className="demo-arrow">→</span>
            </button>
          </div>

          <form onSubmit={handleCustomGoogleSubmit} className="custom-email-form">
            <input
              type="email"
              placeholder="Or enter any Google email (e.g. your.email@gmail.com)"
              value={customEmail}
              onChange={(e) => setCustomEmail(e.target.value)}
              className="custom-email-input"
            />
            <button type="submit" className="custom-email-btn">
              Use Account
            </button>
          </form>

          <div className="auth-footer-note">
            🔒 Strictly isolated per user. Case records, dialogue states & statutory drafts persist to database linked to your Google identity.
          </div>

          {onClose && (
            <button
              type="button"
              className="auth-cancel-btn"
              onClick={onClose}
            >
              ← Back to Home / Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

