/**
 * TypeScript contract for Wysteria DeveloperReport.
 *
 * MAPPING TO BACKEND PYTHON MODELS (wysteria.reporting.models):
 * - ReportStatus <-> wysteria.reporting.models.ReportStatus
 * - StatusBadge <-> wysteria.reporting.models.StatusBadge
 * - StatusPresentation <-> wysteria.reporting.models.StatusPresentation
 * - DiagnosticCategory <-> wysteria.reporting.models.DiagnosticCategory
 * - Severity <-> wysteria.reporting.diagnostics.Severity
 * - SourceLocation <-> wysteria.reporting.diagnostics.SourceLocation
 * - NormalizedDiagnostic <-> wysteria.reporting.models.NormalizedDiagnostic
 * - MatchState <-> wysteria.reporting.models.MatchState
 * - OutputReportItem <-> wysteria.reporting.models.OutputReportItem
 * - AssertionReportItem <-> wysteria.reporting.models.AssertionReportItem
 * - ValidationSummary <-> wysteria.reporting.models.ValidationSummary
 * - ExecutionSummary <-> wysteria.reporting.models.ExecutionSummary
 * - WorkflowIdentity <-> wysteria.reporting.models.WorkflowIdentity
 * - FixtureIdentity <-> wysteria.reporting.models.FixtureIdentity
 * - BaselineDiffEntry <-> wysteria.reporting.models.BaselineDiffEntry
 * - BaselineSummary <-> wysteria.reporting.models.BaselineSummary
 * - NodeExecutionTrace <-> wysteria.verification.models.NodeExecutionTrace
 * - DeveloperReport <-> wysteria.reporting.models.DeveloperReport
 *
 * No fields are renamed or reinterpreted.
 */

export type ReportStatus =
  | 'PASS'
  | 'PASSED'
  | 'FAIL'
  | 'INVALID_WORKFLOW'
  | 'INVALID_FIXTURE'
  | 'RUNTIME_ERROR'
  | 'ASSERTION_FAILED'
  | 'OUTPUT_MISMATCH'
  | 'LIMIT_EXCEEDED'
  | 'REGRESSION';

export type StatusBadgeType = 'success' | 'failure' | 'error';

export interface StatusPresentation {
  status: ReportStatus;
  label: string;
  badge: StatusBadgeType;
  passed: boolean;
}

export type DiagnosticCategory =
  | 'schema'
  | 'reference'
  | 'graph'
  | 'capability'
  | 'semantic'
  | 'baseline'
  | 'fixture'
  | 'runtime'
  | 'assertion'
  | 'output'
  | 'limit'
  | 'system'
  | 'general';

export type Severity = 'error' | 'warning';

export interface SourceLocation {
  file: string;
  line: number;
  column: number;
}

export interface NormalizedDiagnostic {
  code: string;
  severity: Severity;
  message: string;
  category: DiagnosticCategory;
  node_id: string | null;
  path: string;
  location: SourceLocation | null;
  hint: string | null;
}

export type MatchState = 'MATCH' | 'MISMATCH' | 'MISSING' | 'UNEXPECTED' | 'UNCHECKED';

export interface OutputReportItem {
  id: string;
  actual: unknown;
  expected: unknown;
  match_state: MatchState;
}

export interface AssertionReportItem {
  id: string;
  actual: boolean | null;
  expected: boolean | null;
  match_state: MatchState;
}

export interface ValidationSummary {
  workflow_valid: boolean;
  fixture_valid: boolean;
  error_count: number;
  warning_count: number;
}

export interface ExecutionSummary {
  total_nodes_executed: number;
  success: boolean;
  expected_error_occurred: boolean;
  expected_error_code: string | null;
  actual_error_code: string | null;
}

export interface WorkflowIdentity {
  name: string | null;
  fingerprint: string | null;
  display_name: string;
}

export interface FixtureIdentity {
  id: string;
  name: string | null;
  display_name: string;
}

export interface BaselineDiffEntry {
  category: string;
  name: string;
  kind: string;
  expected: unknown;
  actual: unknown;
  message: string;
}

export interface BaselineSummary {
  status: string;
  matches: boolean;
  workflow_changed: boolean;
  workflow_expected: string | null;
  workflow_actual: string | null;
  fixture_changed: boolean;
  fixture_expected: string | null;
  fixture_actual: string | null;
  status_changed: boolean;
  status_expected: string | null;
  status_actual: string | null;
  expected_error_changed: boolean;
  expected_error_expected: string | null;
  expected_error_actual: string | null;
  outputs_changed: boolean;
  output_diffs: BaselineDiffEntry[];
  assertions_changed: boolean;
  assertion_diffs: BaselineDiffEntry[];
  diff_entries: BaselineDiffEntry[];
  reasons: string[];
}

export interface NodeExecutionTrace {
  step: number;
  node_id: string;
  kind: string;
  resolved_inputs: Record<string, unknown>;
  output: unknown;
}

export interface DeveloperReport {
  status: ReportStatus;
  overall_status: ReportStatus;
  status_presentation: StatusPresentation;
  success: boolean;
  workflow: WorkflowIdentity;
  fixture: FixtureIdentity;
  fixture_id: string;
  workflow_fingerprint: string | null;
  validation: ValidationSummary;
  execution: ExecutionSummary;
  outputs: OutputReportItem[];
  assertions: AssertionReportItem[];
  diagnostics: NormalizedDiagnostic[];
  traces: NodeExecutionTrace[];
  actual_outputs: Record<string, unknown>;
  actual_assertions: Record<string, boolean>;
  baseline: BaselineSummary | null;
}
