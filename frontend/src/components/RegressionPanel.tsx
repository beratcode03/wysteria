import React from 'react';
import { BaselineSummary } from '../types/report';

interface RegressionPanelProps {
  baseline: BaselineSummary;
  currentFingerprint: string | null;
}

export const RegressionPanel: React.FC<RegressionPanelProps> = ({
  baseline,
  currentFingerprint,
}) => {
  return (
    <div className="regression-diff-view" aria-label="Regression Detection Panel">
      <div className="diff-view-header">
        <div className="diff-title-group">
          <span className="diff-symbol text-error font-mono" aria-hidden="true">!</span>
          <span className="diff-title font-mono font-bold">REGRESSION DETECTED</span>
        </div>
        <span className="diff-hint font-mono text-muted text-xs">
          baseline contract comparison failed
        </span>
      </div>

      <div className="diff-fingerprints-bar font-mono text-xs">
        <div className="fingerprint-pair">
          <span className="text-muted">Baseline fingerprint:</span>
          <code className="text-secondary" title={baseline.workflow_expected || ''}>
            {baseline.workflow_expected ? `${baseline.workflow_expected.slice(0, 16)}...` : 'none'}
          </code>
        </div>
        <div className="fingerprint-pair">
          <span className="text-muted">Current fingerprint:</span>
          <code className="text-error font-bold" title={currentFingerprint || baseline.workflow_actual || ''}>
            {(currentFingerprint || baseline.workflow_actual) ? `${(currentFingerprint || baseline.workflow_actual)!.slice(0, 16)}...` : 'none'}
          </code>
        </div>
      </div>

      {/* Output diff: git diff style */}
      {baseline.output_diffs.length > 0 && (
        <div className="diff-block">
          <div className="diff-block-header font-mono text-xs text-muted">
            OUTPUT DIFF
          </div>
          <div className="diff-content font-mono text-xs">
            {baseline.output_diffs.map((diff, index) => (
              <div key={index} className="diff-entry">
                <div className="diff-entry-title text-accent">
                  output &apos;{diff.name}&apos;:
                </div>
                <div className="diff-line diff-deletion">
                  <span className="diff-marker">- expected:</span>{' '}
                  <span className="diff-value">{JSON.stringify(diff.expected)}</span>
                </div>
                <div className="diff-line diff-addition">
                  <span className="diff-marker">+ actual:  </span>{' '}
                  <span className="diff-value">{JSON.stringify(diff.actual)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Structured findings table */}
      <div className="structured-findings-section">
        <div className="findings-header font-mono text-xs text-muted">
          STRUCTURED FINDINGS
        </div>
        <table className="findings-table font-mono text-xs">
          <thead>
            <tr>
              <th scope="col">CONTRACT ITEM</th>
              <th scope="col">STATE</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>WORKFLOW FINGERPRINT</td>
              <td>
                <span className={`finding-tag ${baseline.workflow_changed ? 'tag-changed' : 'tag-unchanged'}`}>
                  {baseline.workflow_changed ? 'CHANGED' : 'UNCHANGED'}
                </span>
              </td>
            </tr>
            <tr>
              <td>OUTPUT result</td>
              <td>
                <span className={`finding-tag ${baseline.outputs_changed ? 'tag-changed' : 'tag-unchanged'}`}>
                  {baseline.outputs_changed ? 'CHANGED' : 'UNCHANGED'}
                </span>
              </td>
            </tr>
            <tr>
              <td>ASSERTIONS</td>
              <td>
                <span className={`finding-tag ${baseline.assertions_changed ? 'tag-changed' : 'tag-unchanged'}`}>
                  {baseline.assertions_changed ? 'CHANGED' : '✓ unchanged'}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Baseline reasons if any */}
      {baseline.reasons && baseline.reasons.length > 0 && (
        <div className="reasons-section">
          <div className="reasons-header font-mono text-xs text-muted">REASONS</div>
          <ul className="reasons-list font-mono text-xs">
            {baseline.reasons.map((r, i) => (
              <li key={i} className="reason-item text-error">
                • {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
