import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import App from '../App';
import { mockSuccessfulReport, mockOutputMismatchReport, mockRegressionReport } from '../data/mockReports';
import { VerificationSummary } from '../components/VerificationSummary';
import { OutputList } from '../components/OutputList';
import { AssertionList } from '../components/AssertionList';
import { RegressionPanel } from '../components/RegressionPanel';
import { WorkflowGraph } from '../components/WorkflowGraph';
import { NodeDetails } from '../components/NodeDetails';

describe('Wysteria Engineering UI & Integration', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url === '/api/scenarios') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { id: 'successful-verification', name: 'Successful Verification (PASS)', description: 'desc', workflow: 'wf.yaml', fixture: 'fix.yaml', baseline: null },
            { id: 'failed-output', name: 'Output Mismatch Failure (FAIL)', description: 'desc', workflow: 'wf.yaml', fixture: 'fix.yaml', baseline: null },
            { id: 'regression-result', name: 'Regression Detected (REGRESSION)', description: 'desc', workflow: 'wf.yaml', fixture: 'fix.yaml', baseline: 'base.json' },
            { id: 'runtime-error', name: 'Runtime Pointer Error (ERROR)', description: 'desc', workflow: 'wf.yaml', fixture: 'fix.yaml', baseline: null },
          ]),
        });
      }
      if (url.includes('successful-verification')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockSuccessfulReport),
        });
      }
      if (url.includes('failed-output')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockOutputMismatchReport),
        });
      }
      if (url.includes('regression-result')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockRegressionReport),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockSuccessfulReport),
      });
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Verification workspace by default with Wysteria branding and top tabs', async () => {
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByText('Wysteria')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Verification$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Baselines$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Workflows$/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Verification Workspace')).toBeInTheDocument();
  });

  it('renders PASS report outcome cleanly with semantic symbol', () => {
    render(<VerificationSummary report={mockSuccessfulReport} />);
    expect(screen.getByText('user_transform_flow')).toBeInTheDocument();
    expect(screen.getByText('Trim and Uppercase User Fixture')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: /Status: PASS/i })).toBeInTheDocument();
    expect(screen.getByText('VERIFIED')).toBeInTheDocument();
  });

  it('renders FAIL report outcome with mismatch presentation', () => {
    render(<VerificationSummary report={mockOutputMismatchReport} />);
    expect(screen.getByRole('status', { name: /Status: OUTPUT MISMATCH/i })).toBeInTheDocument();
    expect(screen.getByText('OUTPUT MISMATCH')).toBeInTheDocument();
  });

  it('renders output expected vs actual correctly with diff presentation', () => {
    render(<OutputList outputs={mockOutputMismatchReport.outputs} />);
    expect(screen.getByText('output: result')).toBeInTheDocument();
    expect(screen.getByText(/Welcome, BERATCAN!/)).toBeInTheDocument();
    expect(screen.getByText(/Welcome, BERAT!/)).toBeInTheDocument();
    expect(screen.getByText(/MISMATCH/)).toBeInTheDocument();
  });

  it('renders assertion expected vs actual correctly in dense table', () => {
    render(<AssertionList assertions={mockSuccessfulReport.assertions} />);
    expect(screen.getByText('assert_name_valid')).toBeInTheDocument();
    expect(screen.getByText('check_length')).toBeInTheDocument();
    const matches = screen.getAllByText(/MATCH/);
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });

  it('renders regression panel as code review git diff with structured findings', () => {
    render(
      <RegressionPanel
        baseline={mockRegressionReport.baseline!}
        currentFingerprint={mockRegressionReport.workflow_fingerprint}
      />
    );
    expect(screen.getByText('REGRESSION DETECTED')).toBeInTheDocument();
    expect(screen.getByText(/Welcome, BERATCAN!/)).toBeInTheDocument();
    expect(screen.getByText(/Welcome, BERAT!/)).toBeInTheDocument();
    expect(screen.getByText('WORKFLOW FINGERPRINT')).toBeInTheDocument();
    expect(screen.getByText('OUTPUT result')).toBeInTheDocument();
    expect(screen.getByText('✓ unchanged')).toBeInTheDocument();
  });

  it('handles node selection and displays node verification details', () => {
    let selectedId: string | null = 'trim_user';
    const { rerender } = render(
      <>
        <WorkflowGraph
          traces={mockSuccessfulReport.traces}
          diagnostics={mockSuccessfulReport.diagnostics}
          selectedNodeId={selectedId}
          onSelectNode={(id) => { selectedId = id; }}
        />
        <NodeDetails
          nodeId={selectedId}
          traces={mockSuccessfulReport.traces}
          diagnostics={mockSuccessfulReport.diagnostics}
        />
      </>
    );

    expect(screen.getByText('trim_user', { selector: '.node-id' })).toBeInTheDocument();
    expect(screen.getByTestId('node-output')).toHaveTextContent('berat');

    // Select uppercase_user
    selectedId = 'uppercase_user';
    rerender(
      <>
        <WorkflowGraph
          traces={mockSuccessfulReport.traces}
          diagnostics={mockSuccessfulReport.diagnostics}
          selectedNodeId={selectedId}
          onSelectNode={(id) => { selectedId = id; }}
        />
        <NodeDetails
          nodeId={selectedId}
          traces={mockSuccessfulReport.traces}
          diagnostics={mockSuccessfulReport.diagnostics}
        />
      </>
    );

    expect(screen.getByText('uppercase_user', { selector: '.node-id' })).toBeInTheDocument();
    expect(screen.getByTestId('node-output')).toHaveTextContent('BERAT');
  });

  it('navigates between Verification, Workflows, and Baselines tabs', async () => {
    await act(async () => {
      render(<App />);
    });

    // Navigate to Workflows
    const workflowsTab = screen.getByRole('button', { name: /^Workflows$/i });
    await act(async () => {
      fireEvent.click(workflowsTab);
    });
    expect(screen.getByText('WORKFLOWS & VERIFICATIONS')).toBeInTheDocument();
    expect(screen.getByText('RECENT VERIFICATION RUNS')).toBeInTheDocument();

    // Inspect first workflow from table
    const inspectButtons = await screen.findAllByRole('button', { name: /Inspect/i });
    await act(async () => {
      fireEvent.click(inspectButtons[0]);
    });

    // Back to Verification Workspace
    await waitFor(() => {
      expect(screen.getByLabelText('Verification Workspace')).toBeInTheDocument();
    });

    // Navigate to Baselines
    const baselinesTab = screen.getByRole('button', { name: /^Baselines$/i });
    await act(async () => {
      fireEvent.click(baselinesTab);
    });
    expect(screen.getByText('REGRESSION BASELINES')).toBeInTheDocument();
  });

  it('renders loading state while verification is in flight', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    await act(async () => {
      render(<App />);
    });
    expect(screen.getByRole('status')).toHaveTextContent(/verification in local Python engine/i);
  });

  it('renders error state and retry button when local engine is disconnected', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Connection refused'))));
    await act(async () => {
      render(<App />);
    });
    const errorBanner = await screen.findByRole('alert');
    expect(errorBanner).toHaveTextContent(/ENGINE ERROR:Connection refused/i);
    expect(screen.getByRole('button', { name: /\[retry\]/i })).toBeInTheDocument();
  });
});
