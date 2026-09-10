import React from 'react';
import { StatusBadgeType, ReportStatus } from '../types/report';

interface StatusBadgeProps {
  status?: ReportStatus | string;
  label?: string;
  badge?: StatusBadgeType;
  size?: 'sm' | 'md' | 'lg';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  badge = 'success',
  size = 'md',
}) => {
  const displayLabel = label || status || 'UNKNOWN';

  const getSymbol = () => {
    switch (badge) {
      case 'success':
        return '✓';
      case 'failure':
        return '×';
      case 'error':
        return '!';
      default:
        return '•';
    }
  };

  return (
    <span
      className={`status-badge status-badge-${badge} status-badge-${size}`}
      role="status"
      aria-label={`Status: ${displayLabel}`}
    >
      <span className="badge-symbol" aria-hidden="true">
        {getSymbol()}
      </span>
      <span className="badge-text">{displayLabel}</span>
    </span>
  );
};
