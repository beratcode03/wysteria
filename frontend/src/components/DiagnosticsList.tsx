import React from 'react';
import { NormalizedDiagnostic } from '../types/report';

interface DiagnosticsListProps {
  diagnostics: NormalizedDiagnostic[];
}

export const DiagnosticsList: React.FC<DiagnosticsListProps> = ({ diagnostics }) => {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <div className="tab-pane-content">
        <p className="empty-text font-mono text-xs text-muted">0 diagnostics reported. No contract violations or runtime errors.</p>
      </div>
    );
  }

  return (
    <div className="tab-pane-content" aria-label="Normalized Diagnostics">
      <div className="dense-table-wrapper">
        <table className="dense-table font-mono text-xs" aria-label="Diagnostics findings">
          <thead>
            <tr>
              <th scope="col">SEVERITY</th>
              <th scope="col">CODE</th>
              <th scope="col">CATEGORY</th>
              <th scope="col">TARGET</th>
              <th scope="col">MESSAGE</th>
              <th scope="col">HINT</th>
            </tr>
          </thead>
          <tbody>
            {diagnostics.map((diag, index) => (
              <tr key={index} className={`dense-row diag-row-${diag.severity}`}>
                <td className="col-severity">
                  <span className={`severity-badge severity-${diag.severity}`}>
                    {diag.severity === 'error' ? '!' : '•'} {diag.severity.toUpperCase()}
                  </span>
                </td>
                <td className="col-code font-bold text-error">{diag.code}</td>
                <td className="col-cat text-muted">{diag.category}</td>
                <td className="col-target text-accent">
                  {diag.node_id ? `node:${diag.node_id}` : diag.path || '—'}
                </td>
                <td className="col-msg">{diag.message}</td>
                <td className="col-hint text-warning">{diag.hint || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
