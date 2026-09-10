import React from 'react';
import { NodeExecutionTrace, NormalizedDiagnostic } from '../types/report';

interface NodeDetailsProps {
  nodeId: string | null;
  traces: NodeExecutionTrace[];
  diagnostics: NormalizedDiagnostic[];
}

export const NodeDetails: React.FC<NodeDetailsProps> = ({
  nodeId,
  traces,
  diagnostics,
}) => {
  if (!nodeId) {
    return (
      <div className="inspector-panel" aria-label="Node Inspector">
        <div className="panel-header">
          <span className="panel-title font-mono">NODE INSPECTOR</span>
        </div>
        <div className="inspector-empty">
          <p className="font-mono text-muted text-xs">
            Select a node from the execution graph to inspect its inputs, output, and diagnostics.
          </p>
        </div>
      </div>
    );
  }

  const trace = traces.find((t) => t.node_id === nodeId);
  const nodeDiagnostics = diagnostics.filter((d) => d.node_id === nodeId);
  const hasError = nodeDiagnostics.some((d) => d.severity === 'error');
  const kind = trace?.kind || (nodeDiagnostics.length > 0 ? 'select' : 'node');

  return (
    <div className="inspector-panel" aria-label={`Inspector for node ${nodeId}`}>
      <div className="panel-header">
        <span className="panel-title font-mono">NODE INSPECTOR</span>
        <div className="inspector-status-tags font-mono">
          <span className="tag-kind text-xs">[{kind}]</span>
          <span className={`tag-status text-xs ${hasError ? 'tag-error' : 'tag-success'}`}>
            <span aria-hidden="true">{hasError ? '×' : '✓'}</span> {hasError ? 'FAILED' : 'EVALUATED'}
          </span>
        </div>
      </div>

      <div className="inspector-body">
        <div className="inspector-node-title">
          <span className="text-muted text-xs font-mono">ID:</span>
          <span className="font-mono font-bold text-accent text-sm">{nodeId}</span>
        </div>

        {nodeDiagnostics.length > 0 && (
          <div className="inspector-diagnostics" role="alert">
            <div className="inspector-diag-header font-mono text-xs text-error">
              <span aria-hidden="true">!</span> DIAGNOSTIC FINDINGS
            </div>
            {nodeDiagnostics.map((diag, index) => (
              <div key={index} className="inspector-diag-item">
                <div className="diag-item-meta font-mono text-xs">
                  <span className="diag-code text-error font-bold">{diag.code}</span>
                  <span className="diag-cat text-muted">[{diag.category}]</span>
                </div>
                <div className="diag-item-msg font-mono text-xs">{diag.message}</div>
                {diag.hint && (
                  <div className="diag-item-hint font-mono text-xs text-warning">
                    hint: {diag.hint}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="inspector-section">
          <div className="section-label-bar font-mono text-xs text-muted">
            RESOLVED INPUTS
          </div>
          {trace && Object.keys(trace.resolved_inputs).length > 0 ? (
            <pre className="inspector-code-block font-mono" data-testid="node-inputs">
              <code>{JSON.stringify(trace.resolved_inputs, null, 2)}</code>
            </pre>
          ) : (
            <div className="inspector-no-data font-mono text-muted text-xs">
              No resolved inputs recorded.
            </div>
          )}
        </div>

        <div className="inspector-section">
          <div className="section-label-bar font-mono text-xs text-muted">
            OUTPUT
          </div>
          {trace ? (
            <pre className="inspector-code-block font-mono" data-testid="node-output">
              <code>{JSON.stringify(trace.output, null, 2) ?? 'null'}</code>
            </pre>
          ) : (
            <div className="inspector-no-data font-mono text-muted text-xs">
              Evaluation did not yield output (failed or skipped).
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
