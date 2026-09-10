import React from 'react';
import { AssertionReportItem } from '../types/report';

interface AssertionListProps {
  assertions: AssertionReportItem[];
}

export const AssertionList: React.FC<AssertionListProps> = ({ assertions }) => {
  if (!assertions || assertions.length === 0) {
    return (
      <div className="tab-pane-content">
        <p className="empty-text font-mono text-xs">No workflow assertions declared.</p>
      </div>
    );
  }

  return (
    <div className="tab-pane-content" aria-label="Assertions">
      <div className="dense-table-wrapper">
        <table className="dense-table font-mono text-xs" aria-label="Assertions table">
          <thead>
            <tr>
              <th scope="col">STATE</th>
              <th scope="col">ASSERTION ID</th>
              <th scope="col">EXPECTED</th>
              <th scope="col">ACTUAL</th>
            </tr>
          </thead>
          <tbody>
            {assertions.map((item) => {
              const isMatch = item.match_state === 'MATCH';
              return (
                <tr
                  key={item.id}
                  className={`dense-row ${isMatch ? 'row-pass' : 'row-fail'}`}
                  data-testid={`assertion-row-${item.id}`}
                >
                  <td className="col-status">
                    <span className={`status-pill ${isMatch ? 'pill-pass' : 'pill-fail'}`}>
                      <span aria-hidden="true">{isMatch ? '✓' : '×'}</span> {item.match_state}
                    </span>
                  </td>
                  <td className="col-id font-bold">{item.id}</td>
                  <td className="col-expected text-secondary">
                    <code>{String(item.expected)}</code>
                  </td>
                  <td className={`col-actual ${isMatch ? 'text-success' : 'text-error font-bold'}`}>
                    <code>{String(item.actual)}</code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
