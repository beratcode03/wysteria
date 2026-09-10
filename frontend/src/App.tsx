import React, { useEffect, useState } from 'react';
import { Navbar, AppView } from './components/Navbar';
import { Verification } from './pages/Verification';
import { Dashboard } from './pages/Dashboard';
import { Baselines } from './pages/Baselines';
import { FALLBACK_SCENARIOS, ScenarioSummary, fetchReport, fetchScenarios } from './api/client';
import { DeveloperReport } from './types/report';

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<AppView>('verification');
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>(FALLBACK_SCENARIOS);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(FALLBACK_SCENARIOS[0].id);

  const [reports, setReports] = useState<Record<string, DeveloperReport>>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load scenarios from backend on mount
  useEffect(() => {
    let isMounted = true;
    fetchScenarios()
      .then((data) => {
        if (isMounted && data.length > 0) {
          setScenarios(data);
        }
      })
      .catch(() => {
        // Keeps FALLBACK_SCENARIOS
      });
    return () => {
      isMounted = false;
    };
  }, []);

  // Fetch report for a scenario
  const loadScenarioReport = async (scenarioId: string) => {
    setLoading(true);
    setError(null);
    try {
      const rep = await fetchReport(scenarioId);
      setReports((prev) => ({ ...prev, [scenarioId]: rep }));
    } catch (err: any) {
      setError(err.message || 'Failed to load report from verification server');
    } finally {
      setLoading(false);
    }
  };

  // Preload reports for all scenarios so all views are immediately responsive
  useEffect(() => {
    scenarios.forEach((sc) => {
      fetchReport(sc.id)
        .then((rep) => setReports((prev) => ({ ...prev, [sc.id]: rep })))
        .catch(() => {});
    });
  }, [scenarios]);

  // Ensure current scenario report is loaded
  useEffect(() => {
    if (!reports[selectedScenarioId]) {
      loadScenarioReport(selectedScenarioId);
    }
  }, [selectedScenarioId]);

  const handleOpenReport = (scenarioId: string) => {
    setSelectedScenarioId(scenarioId);
    setCurrentView('verification');
    if (!reports[scenarioId]) {
      loadScenarioReport(scenarioId);
    }
  };

  const handleRetry = () => {
    loadScenarioReport(selectedScenarioId);
  };

  const currentReport = reports[selectedScenarioId] || null;

  return (
    <div className="app-shell">
      <Navbar
        currentView={currentView}
        onSelectView={setCurrentView}
        scenarios={scenarios}
        selectedScenarioId={selectedScenarioId}
        onSelectScenario={setSelectedScenarioId}
      />

      <main className="app-main">
        {currentView === 'verification' && (
          <Verification
            report={currentReport}
            loading={loading}
            error={error}
            onRetry={handleRetry}
            scenarios={scenarios}
            selectedScenarioId={selectedScenarioId}
            onSelectScenario={setSelectedScenarioId}
            onNavigateToWorkflows={() => setCurrentView('workflows')}
          />
        )}

        {currentView === 'baselines' && (
          <Baselines
            scenarios={scenarios}
            reports={reports}
            onInspectScenario={handleOpenReport}
          />
        )}

        {currentView === 'workflows' && (
          <Dashboard
            scenarios={scenarios}
            reports={reports}
            loading={loading}
            error={error}
            onRetry={handleRetry}
            onOpenReport={handleOpenReport}
          />
        )}
      </main>

      <footer className="app-footer-bar font-mono text-xs">
        <div className="footer-bar-inner">
          <span className="footer-item">wysteria v0.1</span>
          <span className="footer-sep">/</span>
          <span className="footer-item">deterministic verifier</span>
          <span className="footer-sep">/</span>
          <span className="footer-item">localhost:8787</span>
          <span className="footer-sep">/</span>
          <span className="footer-item">no-network sandbox</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
