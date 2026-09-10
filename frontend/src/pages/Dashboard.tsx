import React from 'react';
import { ScenarioSummary } from '../api/client';
import { DeveloperReport } from '../types/report';

interface DashboardProps {
  scenarios: ScenarioSummary[];
  reports: Record<string, DeveloperReport>;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onOpenReport: (scenarioId: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  scenarios,
  reports,
  loading,
  error,
  onRetry,
  onOpenReport,
}) => {
  const loadedReports = Object.values(reports);

  const getStatusBadge = (rep?: DeveloperReport) => {
    if (!rep) {
      return <span className="status-pill pill-loading font-mono">LOADING...</span>;
    }
    const status = rep.status;
    if (status === 'PASS' || status === 'PASSED') {
      return <span className="status-pill pill-pass font-mono">✓ PASS</span>;
    }
    if (status === 'OUTPUT_MISMATCH') {
      return <span className="status-pill pill-fail font-mono">× MISMATCH</span>;
    }
    if (status === 'REGRESSION') {
      return <span className="status-pill pill-regression font-mono">! REGRESSION</span>;
    }
    if (status === 'RUNTIME_ERROR') {
      return <span className="status-pill pill-error font-mono">! ERROR</span>;
    }
    return <span className="status-pill font-mono">{status}</span>;
  };

  const getResultSummary = (rep?: DeveloperReport) => {
    if (!rep) return '—';
    if (rep.status === 'PASS' || rep.status === 'PASSED') {
      return `${rep.execution.total_nodes_executed} nodes verified · 0 errors`;
    }
    if (rep.status === 'OUTPUT_MISMATCH') {
      const mismatches = rep.outputs.filter((o) => o.match_state === 'MISMATCH').length;
      return `${mismatches} output mismatch`;
    }
    if (rep.status === 'REGRESSION') {
      return `baseline diff: output modified`;
    }
    if (rep.status === 'RUNTIME_ERROR') {
      const errDiag = rep.diagnostics.find((d) => d.severity === 'error');
      return errDiag ? `${errDiag.code}: ${errDiag.message}` : 'runtime error';
    }
    return rep.status;
  };

  return (
    <div className="workflows-view" aria-label="Workflows Overview">
      <div className="view-header">
        <div className="view-title-group">
          <h1 className="view-title font-mono">WORKFLOWS & VERIFICATIONS</h1>
          <p className="view-subtitle font-mono text-muted text-xs">
            Deterministic contracts evaluated against test fixtures and versioned baselines.
          </p>
        </div>

        <div className="header-stats font-mono text-xs text-muted">
          <span>{scenarios.length} scenarios</span>
          <span className="spec-sep">·</span>
          <span>{loadedReports.filter((r) => r.success).length} passed</span>
          <span className="spec-sep">·</span>
          <span>{loadedReports.filter((r) => !r.success).length} failed</span>
        </div>
      </div>

      {error && (
        <div className="status-strip strip-error font-mono text-xs" role="alert">
          <div className="strip-error-main">
            <span className="strip-symbol text-error" aria-hidden="true">!</span>
            <span className="font-bold">Failed to connect to local Wysteria engine:</span>
            <span className="error-text">{error}</span>
          </div>
          <button type="button" className="btn-inline-action" onClick={onRetry}>
            Retry Connection
          </button>
        </div>
      )}

      {loading && loadedReports.length === 0 && (
        <div className="status-strip strip-loading font-mono text-xs" role="status" aria-live="polite">
          <span className="spinner-sm" aria-hidden="true"></span>
          <span>Connecting to local Wysteria engine and loading reports...</span>
        </div>
      )}

      {/* Dense Recent Verifications Table */}
      <div className="dense-table-panel">
        <div className="panel-header">
          <span className="panel-title font-mono">RECENT VERIFICATION RUNS</span>
        </div>

        <div className="dense-table-wrapper">
          <table className="dense-table font-mono text-xs" aria-label="Verification runs table">
            <thead>
              <tr>
                <th scope="col">STATUS</th>
                <th scope="col">WORKFLOW</th>
                <th scope="col">FIXTURE</th>
                <th scope="col">FINGERPRINT</th>
                <th scope="col">RESULT</th>
                <th scope="col" className="col-action-hdr">ACTION</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((sc) => {
                const rep = reports[sc.id];
                const fp = rep?.workflow_fingerprint;
                const wfName = rep?.workflow.name || sc.workflow.split('/').pop() || sc.id;
                const fixName = rep?.fixture.name || rep?.fixture_id || sc.fixture.split('/').pop() || '—';

                return (
                  <tr key={sc.id} className="dense-row hover-highlight">
                    <td className="col-status">{getStatusBadge(rep)}</td>
                    <td className="col-workflow font-bold text-accent">{wfName}</td>
                    <td className="col-fixture text-secondary">{fixName}</td>
                    <td className="col-fp">
                      <code className="text-muted" title={fp || undefined}>
                        {fp ? `${fp.slice(0, 10)}...` : '—'}
                      </code>
                    </td>
                    <td className="col-result text-secondary">{getResultSummary(rep)}</td>
                    <td className="col-action">
                      <button
                        type="button"
                        className="btn-table-action font-mono text-xs"
                        onClick={() => onOpenReport(sc.id)}
                        aria-label={`Inspect verification report for ${wfName}`}
                      >
                        Inspect →
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
