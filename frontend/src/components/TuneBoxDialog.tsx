import React, { useEffect } from 'react';
import './TuneBoxDialog.css';

export interface TuneBoxDialogProps {
  open: boolean;
  title?: string;
  message: string;
  type?: 'info' | 'warning' | 'error' | 'confirm';
  icon?: string;
  confirmText?: string;
  cancelText?: string;
  thirdText?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
  onThird?: () => void;
}

export const TuneBoxDialog: React.FC<TuneBoxDialogProps> = ({
  open,
  title,
  message,
  type = 'warning',
  icon,
  confirmText = 'OK',
  cancelText,
  thirdText,
  onConfirm,
  onCancel,
  onThird,
}) => {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onCancel) {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const defaultIcon = icon || (
    type === 'error' ? 'error' :
    type === 'info' ? 'info' :
    'warning'
  );

  const defaultTitle = title || (
    type === 'error' ? 'Error' :
    type === 'info' ? 'Information' :
    'Notice'
  );

  return (
    <div className="tunebox-dialog-overlay" onClick={onCancel || onConfirm}>
      <div className="tunebox-dialog-card" onClick={(e) => e.stopPropagation()}>
        <div className="tunebox-dialog-header">
          <span className={`material-symbols-outlined tunebox-dialog-icon ${type}`}>
            {defaultIcon}
          </span>
          <h3 className="tunebox-dialog-title">{defaultTitle}</h3>
        </div>

        <p className="tunebox-dialog-body">{message}</p>

        <div className="tunebox-dialog-actions">
          {thirdText && onThird && (
            <button
              type="button"
              className="tunebox-dialog-btn tunebox-dialog-btn-danger"
              onClick={onThird}
            >
              {thirdText}
            </button>
          )}
          {cancelText && onCancel && (
            <button
              type="button"
              className="tunebox-dialog-btn tunebox-dialog-btn-secondary"
              onClick={onCancel}
            >
              {cancelText}
            </button>
          )}
          {onConfirm && (
            <button
              type="button"
              className="tunebox-dialog-btn tunebox-dialog-btn-primary"
              onClick={onConfirm}
            >
              {confirmText}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default TuneBoxDialog;
