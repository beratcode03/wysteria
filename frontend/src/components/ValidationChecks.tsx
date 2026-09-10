import React from 'react';
import { ValidationSummary } from '../types/report';

interface ValidationChecksProps {
  validation: ValidationSummary;
}

export const ValidationChecks: React.FC<ValidationChecksProps> = ({ validation }) => {
  return (
    <div className="compact-spec-block font-mono text-xs" aria-label="Validation Checks">
      <div className="spec-item">
        <span className="spec-label text-muted">WORKFLOW IR:</span>
        <span className={`spec-value ${validation.workflow_valid ? 'text-success' : 'text-error font-bold'}`}>
          <span aria-hidden="true">{validation.workflow_valid ? '✓' : '×'}</span> {validation.workflow_valid ? 'VALID' : 'INVALID'}
        </span>
      </div>
      <div className="spec-item">
        <span className="spec-label text-muted">FIXTURE:</span>
        <span className={`spec-value ${validation.fixture_valid ? 'text-success' : 'text-error font-bold'}`}>
          <span aria-hidden="true">{validation.fixture_valid ? '✓' : '×'}</span> {validation.fixture_valid ? 'VALID' : 'INVALID'}
        </span>
      </div>
      <div className="spec-item">
        <span className="spec-label text-muted">ERRORS:</span>
        <span className={`spec-value ${validation.error_count > 0 ? 'text-error font-bold' : 'text-muted'}`}>
          {validation.error_count}
        </span>
      </div>
      <div className="spec-item">
        <span className="spec-label text-muted">WARNINGS:</span>
        <span className={`spec-value ${validation.warning_count > 0 ? 'text-warning font-bold' : 'text-muted'}`}>
          {validation.warning_count}
        </span>
      </div>
    </div>
  );
};
