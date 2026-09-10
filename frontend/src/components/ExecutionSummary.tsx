import React from 'react';
import { ExecutionSummary as IExecutionSummary } from '../types/report';

interface ExecutionSummaryProps {
  execution: IExecutionSummary;
}

export const ExecutionSummary: React.FC<ExecutionSummaryProps> = ({ execution }) => {
  return (
    <div className="compact-spec-block font-mono text-xs" aria-label="Execution Summary">
      <div className="spec-item">
        <span className="spec-label text-muted">NODES EXECUTED:</span>
        <span className="spec-value text-secondary font-bold">{execution.total_nodes_executed}</span>
      </div>
      <div className="spec-item">
        <span className="spec-label text-muted">EXECUTION STATUS:</span>
        <span className={`spec-value ${execution.success ? 'text-success' : 'text-error font-bold'}`}>
          <span aria-hidden="true">{execution.success ? '✓' : '×'}</span> {execution.success ? 'COMPLETED' : 'FAILED'}
        </span>
      </div>
      {execution.actual_error_code && (
        <div className="spec-item">
          <span className="spec-label text-muted">ERROR CODE:</span>
          <span className="spec-value text-error font-bold">{execution.actual_error_code}</span>
        </div>
      )}
    </div>
  );
};
