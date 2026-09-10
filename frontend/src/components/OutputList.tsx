import React from 'react';
import { OutputReportItem } from '../types/report';

interface OutputListProps {
  outputs: OutputReportItem[];
}

export const OutputList: React.FC<OutputListProps> = ({ outputs }) => {
  if (!outputs || outputs.length === 0) {
    return (
      <div className="tab-pane-content">
        <p className="empty-text font-mono text-xs">No workflow outputs evaluated.</p>
      </div>
    );
  }

  return (
    <div className="tab-pane-content" aria-label="Outputs">
      <div className="outputs-dense-list">
        {outputs.map((item) => {
          const isMatch = item.match_state === 'MATCH';
          return (
            <div
              key={item.id}
              className={`output-dense-row ${isMatch ? 'match-ok' : 'match-fail'}`}
              data-testid={`output-item-${item.id}`}
            >
              <div className="output-row-header font-mono text-xs">
                <span className="output-id font-bold">output: {item.id}</span>
                <span className={`status-pill ${isMatch ? 'pill-pass' : 'pill-fail'}`}>
                  <span aria-hidden="true">{isMatch ? '✓' : '×'}</span> {item.match_state}
                </span>
              </div>

              <div className="output-diff-view font-mono text-xs">
                <div className="diff-line diff-expected">
                  <span className="diff-prefix text-muted">- expected:</span>
                  <pre className="inline-code">
                    <code>{JSON.stringify(item.expected)}</code>
                  </pre>
                </div>
                <div className={`diff-line ${isMatch ? 'diff-actual-match' : 'diff-actual-mismatch'}`}>
                  <span className="diff-prefix text-muted">+ actual:  </span>
                  <pre className="inline-code">
                    <code>{JSON.stringify(item.actual)}</code>
                  </pre>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
