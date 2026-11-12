import React, { useRef } from 'react';
import { EvidenceDocument, EvidenceGapResponse } from '../types';

interface EvidenceManagerProps {
  documents: EvidenceDocument[];
  gapData: EvidenceGapResponse | null;
  onUpload: (file: File) => void;
  uploading: boolean;
}

export const EvidenceManager: React.FC<EvidenceManagerProps> = ({
  documents,
  gapData,
  onUpload,
  uploading,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onUpload(e.target.files[0]);
    }
  };

  return (
    <div>
      <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#1e293b', marginBottom: 14 }}>
        Evidence Repository & OCR Field Ingestion
      </h3>

      <div
        className="upload-dropzone"
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          onChange={handleFileChange}
          accept="image/*,.pdf"
        />
        <div style={{ fontSize: '1.8rem', marginBottom: 6 }}>📄</div>
        <div style={{ fontWeight: 600, color: '#1e293b', fontSize: '0.9rem' }}>
          {uploading ? 'Processing OCR & parsing layout...' : 'Click to Upload Invoice / Chat Screenshot / Product Photo'}
        </div>
        <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 4 }}>
          Supports PDF, PNG, JPG (Automated OCR Field Extraction)
        </div>
      </div>

      {gapData && (
        <div className="checklist-card">
          <div className="readiness-meter">
            <span style={{ fontWeight: 700, fontSize: '0.9rem', color: '#1e293b' }}>
              Case Readiness Score
            </span>
            <span style={{ fontWeight: 800, fontSize: '1.2rem', color: '#10b981' }}>
              {gapData.readiness_score.toFixed(0)}%
            </span>
          </div>

          <div style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: 10 }}>
            Statutory evidence requirements for <strong>{gapData.issue_category || 'Grievance'}</strong>:
          </div>

          <div className="checklist-items">
            {Object.entries(gapData.checklist || {}).map(([item, isPresent]) => (
              <div key={item} className="checklist-row">
                <span style={{ color: isPresent ? '#10b981' : '#ef4444', fontWeight: 700 }}>
                  {isPresent ? '☑' : '☐'}
                </span>
                <span style={{ textDecoration: isPresent ? 'none' : 'none', color: isPresent ? '#1e293b' : '#64748b' }}>
                  {item}
                </span>
                <span style={{ fontSize: '0.7rem', marginLeft: 'auto', color: isPresent ? '#10b981' : '#f59e0b', fontWeight: 600 }}>
                  {isPresent ? 'Verified' : 'Required'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {documents.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 10 }}>
            Ingested Documents ({documents.length})
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {documents.map((doc) => (
              <div
                key={doc.id}
                style={{
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: 6,
                  padding: '10px 14px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{doc.filename}</div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
                    Type: {doc.file_type.toUpperCase()} • Status: {doc.processing_status}
                  </div>
                </div>
                {doc.extracted_fields?.total_amount && (
                  <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#2563eb' }}>
                    OCR Amount: ₹{doc.extracted_fields.total_amount}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

