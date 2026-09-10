import React, { useState } from 'react';
import { DeveloperReport } from '../types/report';

interface VerificationSummaryProps {
  report: DeveloperReport;
}

export const VerificationSummary: React.FC<VerificationSummaryProps> = ({ report }) => {
  const [copied, setCopied] = useState(false);

  const copyFingerprint = () => {
    if (report.workflow_fingerprint) {
      navigator.clipboard?.writeText(report.workflow_fingerprint);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  const getStatusTag = () => {
    const status = report.status;
    if (status === 'PASS' || status === 'PASSED') {
      return { symbol: '✓', label: 'VERIFIED', cls: 'status-tag-pass' };
    }
    if (status === 'OUTPUT_MISMATCH') {
      return { symbol: '×', label: 'OUTPUT MISMATCH', cls: 'status-tag-fail' };
    }
    if (status === 'REGRESSION') {
      return { symbol: '!', label: 'REGRESSION DETECTED', cls: 'status-tag-regression' };
    }
    if (status === 'RUNTIME_ERROR') {
      return { symbol: '!', label: 'RUNTIME ERROR', cls: 'status-tag-error' };
    }
    return { symbol: '•', label: status, cls: 'status-tag-default' };
  };

  const statusTag = getStatusTag();
  const totalNodes = report.execution?.total_nodes_executed || report.traces?.length || 0;
  const workflowName = report.workflow.display_name || report.workflow.name || 'workflow';
  const fixtureName = report.fixture.display_name || report.fixture.name || report.fixture_id || 'fixture';
  const fp = report.workflow_fingerprint;

  return (
    <div className="verification-header" aria-label="Verification Workspace Header">
      <div className="header-primary-row">
        <div className="header-identity">
          <div className="header-title-line">
            <span
              className={`header-status-tag ${statusTag.cls}`}
              role="status"
              aria-label={`Status: ${report.status_presentation.label}`}
            >
              <span className="status-symbol" aria-hidden="true">{statusTag.symbol}</span>
              <span className="status-text">{statusTag.label}</span>
            </span>
            <h1 className="header-workflow-name font-mono">{workflowName}</h1>
          </div>

          <div className="header-fixture-line">
            <span className="fixture-label text-muted">fixture:</span>
            <span className="fixture-value font-mono">{fixtureName}</span>
          </div>
        </div>

        <div className="header-actions">
          {report.baseline && !report.baseline.matches && (
            <span className="header-regression-badge font-mono">
              ! Baseline mismatch
            </span>
          )}
        </div>
      </div>

      <div className="header-meta-row">
        <div className="header-fingerprint-line">
          <span className="meta-label text-muted">fingerprint:</span>
          <code className="meta-fingerprint font-mono" title={fp || undefined}>
            {fp ? `${fp.slice(0, 16)}...${fp.slice(-8)}` : 'none'}
          </code>
          {fp && (
            <button
              type="button"
              className="btn-copy-fp font-mono"
              onClick={copyFingerprint}
              aria-label="Copy full workflow fingerprint"
            >
              {copied ? 'copied' : 'copy'}
            </button>
          )}
        </div>

        <div className="header-specs font-mono text-muted text-xs">
          <span>{totalNodes} nodes</span>
          <span className="spec-sep">·</span>
          <span>deterministic</span>
          <span className="spec-sep">·</span>
          <span>sandbox</span>
          <span className="spec-sep">·</span>
          <span>ir v1</span>
        </div>
      </div>
    </div>
  );
};
