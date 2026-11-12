import React, { useState, useEffect, useRef } from 'react';
import { DialogueTurn, ExtractedEntity } from '../types';

interface ChatPanelProps {
  turns: DialogueTurn[];
  onSendMessage: (message: string) => Promise<boolean | void> | void;
  onUploadEvidence?: (file: File) => Promise<void>;
  onSkipEvidence?: () => void;
  latestEntities: ExtractedEntity[];
  loading: boolean;
  uploading?: boolean;
  workflowStage?: string;
  activeCaseCategory?: string | null;
  activeCasePlatform?: string | null;
  errorMessage?: string | null;
  onClearError?: () => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  turns,
  onSendMessage,
  onUploadEvidence,
  onSkipEvidence,
  latestEntities,
  loading,
  uploading,
  workflowStage,
  activeCaseCategory,
  activeCasePlatform,
  errorMessage,
  onClearError,
}) => {
  const [input, setInput] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [optimisticTurn, setOptimisticTurn] = useState<DialogueTurn | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Clear optimistic turn when real turns update from backend
  useEffect(() => {
    setOptimisticTurn(null);
  }, [turns]);

  // Auto-scroll to the bottom whenever turns change, optimistic turn is added, or loading updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns, optimisticTurn, loading]);

  const adjustTextareaHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const textToSend = input.trim();
    if (!textToSend && !selectedFile) return;
    if (loading || uploading) return;

    // If file is selected, upload it via evidence handler
    if (selectedFile && onUploadEvidence) {
      const fileToUpload = selectedFile;
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      
      // Optimistically add user turn for upload
      setOptimisticTurn({
        id: 'optimistic-upload-temp',
        role: 'user',
        message: `📎 Uploading evidence: ${fileToUpload.name}...`,
        turn_number: (turns.length || 0) + 1,
      });

      try {
        await onUploadEvidence(fileToUpload);
        if (textToSend) {
          await onSendMessage(textToSend);
          setInput('');
        }
      } catch (err) {
        console.error('Evidence upload error:', err);
      } finally {
        setOptimisticTurn(null);
      }
      return;
    }

    // Immediately show the user message in the chat feed
    setOptimisticTurn({
      id: 'optimistic-temp-id',
      role: 'user',
      message: textToSend,
      turn_number: (turns.length || 0) + 1,
    });
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const result = await onSendMessage(textToSend);
      if (result === false) {
        // Failed: restore input and remove optimistic message
        setInput(textToSend);
        setOptimisticTurn(null);
      }
    } catch (err) {
      setInput(textToSend);
      setOptimisticTurn(null);
    }
  };

  // Helper to render markdown bolding (**bold text**) and entity highlights cleanly
  const renderFormattedMessage = (text: string) => {
    if (!text) return null;
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        const inner = part.slice(2, -2);
        return (
          <strong key={i} className="highlighted-text-badge">
            {inner}
          </strong>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="chat-panel-container">
      {/* Top Banner / Case Title */}
      <div className="chat-top-bar">
        <div className="active-case-summary">
          <span className="case-title-label">Active Grievance:</span>
          <span className="case-title-bold">
            {activeCasePlatform ? `${activeCasePlatform} — ` : ''}
            {activeCaseCategory || 'Intake in Progress'}
          </span>
        </div>
        <div className="chat-active-indicator">
          <span className="live-dot"></span>
          <span>DST Active</span>
        </div>
      </div>

      {/* Scrollable Messages Container */}
      <div className="chat-messages-scroll-area">
        {(() => {
          const allTurns = optimisticTurn ? [...turns, optimisticTurn] : turns;
          if (allTurns.length === 0) {
            return (
              <div className="chat-welcome-card">
                <div className="welcome-icon">⚖️</div>
                <h3>Describe Your Consumer Grievance</h3>
                <p>
                  Tell me what happened with your order (e.g. on Amazon, Flipkart, Zepto, Blinkit, Swiggy Instamart).
                </p>
                <div className="welcome-examples">
                  <span className="example-label">Try saying:</span>
                  <button
                    type="button"
                    className="example-prompt-chip"
                    onClick={() =>
                      setInput('I ordered groceries worth ₹523 from Zepto (ZPT-20261107-33254) and was charged above printed MRP.')
                    }
                  >
                    "Charged above MRP on Zepto for ₹523..."
                  </button>
                  <button
                    type="button"
                    className="example-prompt-chip"
                    onClick={() =>
                      setInput('Flipkart marked my ₹32,999 phone order (OD1122334455) as delivered, but it was never delivered to my address.')
                    }
                  >
                    "Non-delivery on Flipkart for phone..."
                  </button>
                </div>
              </div>
            );
          }

          return allTurns.map((t, idx) => (
            <div
              key={t.id || `turn-${idx}`}
              className={`chat-message-row ${t.role === 'user' ? 'row-user' : 'row-assistant'}`}
            >
              <div className={`chat-bubble ${t.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>
                <div className="bubble-content">{renderFormattedMessage(t.message)}</div>
              </div>
            </div>
          ));
        })()}

        {(loading || uploading) && (
          <div className="chat-message-row row-assistant">
            <div className="chat-bubble bubble-assistant typing-bubble">
              <div className="typing-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <span className="typing-text">
                {uploading
                  ? "Processing document OCR & updating statutory checklist..."
                  : "Analyzing legal context & updating slots..."}
              </span>
            </div>
          </div>
        )}

        {/* Scroll anchor */}
        <div ref={messagesEndRef} style={{ height: 1 }} />
      </div>

      {/* Pinned Bottom Input Bar */}
      <form className="chat-input-fixed-bar" onSubmit={handleSubmit}>
        {/* Stage 4 Skip Action Escape Hatch */}
        {workflowStage?.includes('4.') && (
          <div className="chat-stage4-actions-bar">
            <span className="stage4-hint">📎 Evidence Ingestion Active:</span>
            <button
              type="button"
              className="stage4-skip-btn"
              onClick={() => {
                if (onSkipEvidence) onSkipEvidence();
                else onSendMessage('skip');
              }}
              disabled={loading || uploading}
            >
              ⏩ Skip / Proceed to Stage 5: Timeline Reconstruction
            </button>
          </div>
        )}

        {/* Pending File Attachment Preview Badge */}
        {selectedFile && (
          <div className="chat-pending-file-card">
            <span className="file-badge-icon">📄</span>
            <div className="file-badge-info">
              <span className="file-badge-name">{selectedFile.name}</span>
              <span className="file-badge-size">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
            </div>
            <button
              type="button"
              className="file-badge-remove"
              title="Remove attachment"
              onClick={() => {
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}
            >
              ✕
            </button>
          </div>
        )}

        {errorMessage && (
          <div className="chat-error-banner">
            <span>⚠️ {errorMessage}</span>
            {onClearError && (
              <button type="button" onClick={onClearError} className="error-close-btn" aria-label="Dismiss error">
                ✕
              </button>
            )}
          </div>
        )}
        <div className="chat-input-wrap">
          {/* File Picker Trigger */}
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            accept=".pdf,.png,.jpg,.jpeg,.webp,.mp4,.mov"
            onChange={(e) => {
              if (e.target.files && e.target.files[0]) {
                setSelectedFile(e.target.files[0]);
              }
            }}
          />
          <button
            type="button"
            className="chat-attach-btn"
            title="Attach Evidence (PDF, Image, Video)"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading || uploading}
          >
            +
          </button>
          <textarea
            ref={textareaRef}
            rows={1}
            className="chat-text-input"
            placeholder={
              selectedFile
                ? `Attached: ${selectedFile.name} — Click Send or type a note...`
                : "Type details or attach invoice/screenshot with + ..."
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading || uploading}
          />
          <button
            type="submit"
            className="chat-send-submit-btn"
            disabled={loading || uploading || (!input.trim() && !selectedFile)}
          >
            {uploading ? 'Uploading...' : 'Send ↵'}
          </button>
        </div>
      </form>
    </div>
  );
};
