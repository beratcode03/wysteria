import { DeveloperReport } from '../types/report';

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  workflow: string;
  fixture: string;
  baseline: string | null;
}

export const FALLBACK_SCENARIOS: ScenarioSummary[] = [
  {
    id: 'successful-verification',
    name: 'Successful Verification (PASS)',
    description: 'Deterministic execution of user_transform_flow against happy-path fixture. All assertions and outputs match.',
    workflow: 'examples/workflows/user_transform_flow.yaml',
    fixture: 'examples/fixtures/fixture_trim_upper.yaml',
    baseline: null,
  },
  {
    id: 'failed-output',
    name: 'Output Mismatch Failure (FAIL)',
    description: 'Workflow produced "Welcome, BERAT!" but fixture strictly expected "Welcome, BERATCAN!".',
    workflow: 'examples/workflows/user_transform_flow.yaml',
    fixture: 'examples/fixtures/fixture_mismatch.yaml',
    baseline: null,
  },
  {
    id: 'regression-result',
    name: 'Regression Detected (REGRESSION)',
    description: 'Workflow proposal changed greeting output contract and fingerprint. Baseline diff flags output regression while assertions remain unchanged.',
    workflow: 'examples/workflows/user_transform_proposal.yaml',
    fixture: 'examples/fixtures/fixture_trim_upper.yaml',
    baseline: 'examples/baselines/user_transform_baseline.json',
  },
  {
    id: 'runtime-error',
    name: 'Runtime Pointer Error (ERROR)',
    description: 'Select node failed at runtime due to missing JSON pointer segment in fixture input.',
    workflow: 'examples/workflows/data_extractor.yaml',
    fixture: 'examples/fixtures/fixture_missing_email.yaml',
    baseline: null,
  },
];

export async function fetchScenarios(): Promise<ScenarioSummary[]> {
  const res = await fetch('/api/scenarios');
  if (!res.ok) {
    throw new Error(`Failed to load scenarios from engine (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchReport(scenarioId: string): Promise<DeveloperReport> {
  const res = await fetch(`/api/report?scenario=${encodeURIComponent(scenarioId)}`);
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.error || `Verification failed (HTTP ${res.status})`);
  }
  return res.json();
}

export async function verifyPaths(payload: {
  workflow_path: string;
  fixture_path: string;
  baseline_path?: string;
}): Promise<DeveloperReport> {
  const res = await fetch('/api/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.error || `Verification failed (HTTP ${res.status})`);
  }
  return res.json();
}
