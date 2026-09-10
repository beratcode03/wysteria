import React from 'react';
import { NodeExecutionTrace, NormalizedDiagnostic } from '../types/report';

export interface GraphNodeData {
  id: string;
  kind: string;
  step?: number;
  status: 'passed' | 'failed' | 'skipped';
  trace?: NodeExecutionTrace;
  diagnostic?: NormalizedDiagnostic;
}

interface WorkflowGraphProps {
  traces: NodeExecutionTrace[];
  diagnostics: NormalizedDiagnostic[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

export const WorkflowGraph: React.FC<WorkflowGraphProps> = ({
  traces,
  diagnostics,
  selectedNodeId,
  onSelectNode,
}) => {
  const nodes: GraphNodeData[] = [];
  const visited = new Set<string>();

  traces.forEach((trace) => {
    const diag = diagnostics.find((d) => d.node_id === trace.node_id && d.severity === 'error');
    nodes.push({
      id: trace.node_id,
      kind: trace.kind,
      step: trace.step,
      status: diag ? 'failed' : 'passed',
      trace,
      diagnostic: diag,
    });
    visited.add(trace.node_id);
  });

  diagnostics.forEach((diag) => {
    if (diag.node_id && !visited.has(diag.node_id)) {
      nodes.push({
        id: diag.node_id,
        kind: 'select',
        status: diag.severity === 'error' ? 'failed' : 'passed',
        diagnostic: diag,
      });
      visited.add(diag.node_id);
    }
  });

  if (nodes.length === 0) {
    return (
      <div className="graph-panel">
        <div className="panel-header">
          <span className="panel-title font-mono">WORKFLOW GRAPH</span>
        </div>
        <p className="empty-text font-mono text-xs">No graph nodes recorded.</p>
      </div>
    );
  }

  return (
    <div className="graph-panel">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-title font-mono">EXECUTION GRAPH</span>
          <span className="panel-count font-mono text-muted text-xs">{nodes.length} nodes</span>
        </div>
        <span className="panel-hint text-muted text-xs">click node to inspect</span>
      </div>

      <div className="graph-viewport" role="region" aria-label="Workflow graph DAG">
        <div className="graph-boundary-node">
          <span className="boundary-label font-mono">INPUTS</span>
        </div>

        <div className="dag-edge" aria-hidden="true">
          <span className="edge-line"></span>
          <span className="edge-arrow">↓</span>
        </div>

        {nodes.map((node, index) => {
          const isSelected = selectedNodeId === node.id;
          const isPassed = node.status === 'passed';
          const stepNum = typeof node.step === 'number' ? String(node.step).padStart(2, '0') : `--`;

          return (
            <React.Fragment key={node.id}>
              <div
                role="button"
                tabIndex={0}
                aria-pressed={isSelected}
                aria-label={`Node ${node.id}, kind ${node.kind}, status ${node.status}`}
                className={`dag-node ${isPassed ? 'node-pass' : 'node-fail'} ${isSelected ? 'node-selected' : ''}`}
                onClick={() => onSelectNode(node.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectNode(node.id);
                  }
                }}
                data-testid={`graph-node-${node.id}`}
              >
                <div className="dag-node-left">
                  <span className="node-step font-mono text-muted">{stepNum}</span>
                  <div className="node-info">
                    <span className="node-id font-mono font-bold">{node.id}</span>
                    <span className="node-kind font-mono text-muted">[{node.kind}]</span>
                  </div>
                </div>

                <div className="dag-node-right">
                  <span className={`node-status-tag font-mono text-xs ${isPassed ? 'status-pass' : 'status-fail'}`}>
                    <span aria-hidden="true">{isPassed ? '✓' : '×'}</span> {isPassed ? 'PASS' : 'FAIL'}
                  </span>
                </div>
              </div>

              {index < nodes.length - 1 && (
                <div className="dag-edge" aria-hidden="true">
                  <span className="edge-line"></span>
                  <span className="edge-arrow">↓</span>
                </div>
              )}
            </React.Fragment>
          );
        })}

        <div className="dag-edge" aria-hidden="true">
          <span className="edge-line"></span>
          <span className="edge-arrow">↓</span>
        </div>

        <div className="graph-boundary-node">
          <span className="boundary-label font-mono">OUTPUTS & ASSERTIONS</span>
        </div>
      </div>
    </div>
  );
};
