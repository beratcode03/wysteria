import React, { useState, useEffect } from 'react';
import { ScenarioSummary } from '../api/client';
import { DeveloperReport } from '../types/report';
import { VerificationSummary } from '../components/VerificationSummary';
import { ValidationChecks } from '../components/ValidationChecks';
import { ExecutionSummary } from '../components/ExecutionSummary';
import { WorkflowGraph } from '../components/WorkflowGraph';
import { NodeDetails } from '../components/NodeDetails';
import { OutputList } from '../components/OutputList';
import { AssertionList } from '../components/AssertionList';
import { RegressionPanel } from '../components/RegressionPanel';
import { DiagnosticsList } from '../components/DiagnosticsList';
import { ExecutionTrace } from '../components/ExecutionTrace';

interface VerificationProps {
  report: DeveloperReport | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  scenarios: ScenarioSummary[];
  selectedScenarioId: string;
  onSelectScenario: (id: string) => void;
  onNavigateToWorkflows?: () => void;
}

type TabType = 'assertions' | 'outputs' | 'diagnostics' | 'trace' | 'regression';

export const Verification: React.FC<VerificationProps> = ({
  report,
  loading,
  error,
  onRetry,
  scenarios: _scenarios,
  selectedScenarioId: _selectedScenarioId,
  onSelectScenario: _onSelectScenario,
  onNavigateToWorkflows: _onNavigateToWorkflows,
}) => {
  const initialNodeId =
    report?.traces && report.traces.length > 0
      ? report.traces[0].node_id
      : report?.diagnostics[0]?.node_id || null;
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(initialNodeId);

  // Auto-select tab based on failure type or default
  const getDefaultTab = (rep: DeveloperReport | null): TabType => {
    if (!rep) return 'assertions';
    if (rep.baseline && !rep.baseline.matches) return 'regression';
    if (rep.diagnostics && rep.diagnostics.some((d) => d.severity === 'error')) return 'diagnostics';
    if (rep.outputs && rep.outputs.some((o) => o.match_state === 'MISMATCH')) return 'outputs';
    return 'assertions';
  };

  const [activeTab, setActiveTab] = useState<TabType>(getDefaultTab(report));

  useEffect(() => {
    if (report) {
      const node = report.traces && report.traces.length > 0
        ? report.traces[0].node_id
        : report.diagnostics[0]?.node_id || null;
      setSelectedNodeId(node);
      setActiveTab(getDefaultTab(report));
    }
  }, [report?.workflow_fingerprint, report?.status]);

  return (
    <div className="workspace-view" aria-label="Verification Workspace">
      {loading && (
        <div className="status-strip strip-loading font-mono text-xs" role="status" aria-live="polite">
          <span className="spinner-sm" aria-hidden="true"></span>
          <span>executing deterministic verification in local Python engine...</span>
        </div>
      )}

      {error && (
        <div className="status-strip strip-error font-mono text-xs" role="alert">
          <div className="strip-error-main">
            <span className="strip-symbol text-error" aria-hidden="true">!</span>
            <span className="font-bold">ENGINE ERROR:</span>
            <span className="error-text">{error}</span>
          </div>
          <button type="button" className="btn-inline-action" onClick={onRetry}>
            [retry]
          </button>
        </div>
      )}

      {!loading && !error && !report && (
        <div className="panel-empty font-mono text-xs text-muted">
          No verification report loaded.
        </div>
      )}

      {report && (
        <>
          {/* Header */}
          <VerificationSummary report={report} />

          {/* Compact Metadata Strip */}
          <div className="specs-strip">
            <ValidationChecks validation={report.validation} />
            <span className="specs-strip-divider" aria-hidden="true">|</span>
            <ExecutionSummary execution={report.execution} />
          </div>

          {/* Main Layout: Left/Center Workflow Graph, Right Node Inspector */}
          <div className="workspace-main-grid">
            <div className="grid-graph-col">
              <WorkflowGraph
                traces={report.traces}
                diagnostics={report.diagnostics}
                selectedNodeId={selectedNodeId}
                onSelectNode={(id) => setSelectedNodeId(id)}
              />
            </div>

            <div className="grid-inspector-col">
              <NodeDetails
                nodeId={selectedNodeId}
                traces={report.traces}
                diagnostics={report.diagnostics}
              />
            </div>
          </div>

          {/* Below: Tabs for Assertions | Outputs | Diagnostics | Trace | (Regression) */}
          <div className="workspace-sub-panel">
            <div className="sub-panel-tabs" role="tablist" aria-label="Verification Details Tabs">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'assertions'}
                className={`tab-btn font-mono text-xs ${activeTab === 'assertions' ? 'active' : ''}`}
                onClick={() => setActiveTab('assertions')}
              >
                Assertions ({report.assertions?.length || 0})
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'outputs'}
                className={`tab-btn font-mono text-xs ${activeTab === 'outputs' ? 'active' : ''}`}
                onClick={() => setActiveTab('outputs')}
              >
                Outputs ({report.outputs?.length || 0})
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'diagnostics'}
                className={`tab-btn font-mono text-xs ${activeTab === 'diagnostics' ? 'active' : ''} ${
                  report.diagnostics?.length > 0 ? 'tab-has-diagnostics' : ''
                }`}
                onClick={() => setActiveTab('diagnostics')}
              >
                Diagnostics ({report.diagnostics?.length || 0})
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'trace'}
                className={`tab-btn font-mono text-xs ${activeTab === 'trace' ? 'active' : ''}`}
                onClick={() => setActiveTab('trace')}
              >
                Trace ({report.traces?.length || 0})
              </button>

              {report.baseline && !report.baseline.matches && (
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === 'regression'}
                  className={`tab-btn font-mono text-xs tab-regression ${activeTab === 'regression' ? 'active' : ''}`}
                  onClick={() => setActiveTab('regression')}
                >
                  ! Regression Diff
                </button>
              )}
            </div>

            <div className="sub-panel-viewport" role="tabpanel">
              {activeTab === 'assertions' && <AssertionList assertions={report.assertions} />}
              {activeTab === 'outputs' && <OutputList outputs={report.outputs} />}
              {activeTab === 'diagnostics' && <DiagnosticsList diagnostics={report.diagnostics} />}
              {activeTab === 'trace' && <ExecutionTrace traces={report.traces} />}
              {activeTab === 'regression' && report.baseline && (
                <RegressionPanel
                  baseline={report.baseline}
                  currentFingerprint={report.workflow_fingerprint}
                />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
