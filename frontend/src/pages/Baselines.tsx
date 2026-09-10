import React from 'react';
import { ScenarioSummary } from '../api/client';
import { DeveloperReport } from '../types/report';
import { RegressionPanel } from '../components/RegressionPanel';

interface BaselinesProps {
  scenarios: ScenarioSummary[];
  reports: Record<string, DeveloperReport>;
  onInspectScenario: (id: string) => void;
}

export const Baselines: React.FC<BaselinesProps> = ({
  scenarios,
  reports,
  onInspectScenario,
}) => {
  const baselineScenarios = scenarios.filter((s) => s.baseline !== null);
  const regressionScenarios = baselineScenarios.filter((s) => {
    const rep = reports[s.id];
    return rep?.baseline && !rep.baseline.matches;
  });

  return (
    <div className="baselines-view" aria-label="Baselines View">
      <div className="view-header">
        <div className="view-title-group">
          <h1 className="view-title font-mono">REGRESSION BASELINES</h1>
          <p className="view-subtitle font-mono text-muted text-xs">
            Recorded execution contracts against Git-tracked baseline artifacts.
          </p>
        </div>

        <div className="header-stats font-mono text-xs text-muted">
          <span>{baselineScenarios.length} baseline contracts</span>
          <span className="spec-sep">·</span>
          <span className={regressionScenarios.length > 0 ? 'text-error font-bold' : 'text-success'}>
            {regressionScenarios.length} regressions detected
          </span>
        </div>
      </div>

      {baselineScenarios.length === 0 ? (
        <div className="panel-empty font-mono text-xs text-muted">
          No baseline contracts configured for active scenarios.
        </div>
      ) : (
        <div className="baselines-grid">
          {baselineScenarios.map((sc) => {
            const rep = reports[sc.id];
            const hasRegression = rep?.baseline && !rep.baseline.matches;
            const wfName = rep?.workflow.name || sc.workflow.split('/').pop() || sc.id;

            return (
              <div key={sc.id} className="baseline-entry-card">
                <div className="baseline-entry-header">
                  <div className="baseline-identity font-mono">
                    <span className="baseline-wf font-bold text-accent">{wfName}</span>
                    <span className="baseline-file text-muted text-xs">[{sc.baseline}]</span>
                  </div>

                  <div className="baseline-actions">
                    <span className={`status-pill ${hasRegression ? 'pill-regression' : 'pill-pass'}`}>
                      {hasRegression ? '! REGRESSION' : '✓ MATCH'}
                    </span>
                    <button
                      type="button"
                      className="btn-table-action font-mono text-xs"
                      onClick={() => onInspectScenario(sc.id)}
                    >
                      Workspace →
                    </button>
                  </div>
                </div>

                {rep?.baseline && (
                  <div className="baseline-diff-container">
                    <RegressionPanel
                      baseline={rep.baseline}
                      currentFingerprint={rep.workflow_fingerprint}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
