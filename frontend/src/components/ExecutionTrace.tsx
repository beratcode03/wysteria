import React from 'react';
import { NodeExecutionTrace } from '../types/report';

interface ExecutionTraceProps {
  traces: NodeExecutionTrace[];
}

export const ExecutionTrace: React.FC<ExecutionTraceProps> = ({ traces }) => {
  if (!traces || traces.length === 0) {
    return (
      <div className="tab-pane-content">
        <p className="empty-text font-mono text-xs">No execution trace recorded.</p>
      </div>
    );
  }

  return (
    <div className="tab-pane-content" aria-label="Execution Trace">
      <div className="dense-table-wrapper">
        <table className="dense-table font-mono text-xs" aria-label="Deterministic trace log">
          <thead>
            <tr>
              <th scope="col">STEP</th>
              <th scope="col">NODE ID</th>
              <th scope="col">KIND</th>
              <th scope="col">RESOLVED INPUTS</th>
              <th scope="col">OUTPUT</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((trace) => (
              <tr key={trace.step} className="dense-row">
                <td className="col-step text-muted">{String(trace.step).padStart(2, '0')}</td>
                <td className="col-node-id font-bold text-accent">{trace.node_id}</td>
                <td className="col-kind text-muted">[{trace.kind}]</td>
                <td className="col-inputs">
                  <pre className="compact-json">
                    <code>{JSON.stringify(trace.resolved_inputs)}</code>
                  </pre>
                </td>
                <td className="col-output">
                  <pre className="compact-json">
                    <code>{JSON.stringify(trace.output)}</code>
                  </pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
