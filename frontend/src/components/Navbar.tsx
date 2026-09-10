import React from 'react';
import { ScenarioSummary } from '../api/client';

export type AppView = 'verification' | 'baselines' | 'workflows';

interface NavbarProps {
  currentView: AppView;
  onSelectView: (view: AppView) => void;
  scenarios: ScenarioSummary[];
  selectedScenarioId: string;
  onSelectScenario: (id: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentView,
  onSelectView,
  scenarios,
  selectedScenarioId,
  onSelectScenario,
}) => {
  return (
    <header className="navbar">
      <div className="navbar-left">
        <div className="navbar-brand" onClick={() => onSelectView('verification')} role="button" tabIndex={0}>
          <span className="brand-name">Wysteria</span>
          <span className="brand-version">v0.1</span>
        </div>

        <nav className="nav-links" aria-label="Main Navigation">
          <button
            type="button"
            className={`nav-link ${currentView === 'verification' ? 'active' : ''}`}
            onClick={() => onSelectView('verification')}
            aria-current={currentView === 'verification' ? 'page' : undefined}
          >
            Verification
          </button>
          <button
            type="button"
            className={`nav-link ${currentView === 'baselines' ? 'active' : ''}`}
            onClick={() => onSelectView('baselines')}
            aria-current={currentView === 'baselines' ? 'page' : undefined}
          >
            Baselines
          </button>
          <button
            type="button"
            className={`nav-link ${currentView === 'workflows' ? 'active' : ''}`}
            onClick={() => onSelectView('workflows')}
            aria-current={currentView === 'workflows' ? 'page' : undefined}
          >
            Workflows
          </button>
        </nav>
      </div>

      <div className="navbar-right">
        {scenarios.length > 0 && (
          <div className="scenario-picker">
            <label htmlFor="scenario-select" className="scenario-picker-label">
              Scenario:
            </label>
            <select
              id="scenario-select"
              className="scenario-select"
              value={selectedScenarioId}
              onChange={(e) => {
                onSelectScenario(e.target.value);
                if (currentView !== 'verification' && currentView !== 'baselines') {
                  onSelectView('verification');
                }
              }}
            >
              {scenarios.map((sc) => (
                <option key={sc.id} value={sc.id}>
                  {sc.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="server-status-pill" title="Connected to local deterministic verification engine">
          <span className="server-indicator-dot" aria-hidden="true">●</span>
          <span className="server-host font-mono">127.0.0.1:8787</span>
        </div>
      </div>
    </header>
  );
};
