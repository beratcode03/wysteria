import { DeveloperReport } from '../types/report';

export const mockSuccessfulReport: DeveloperReport = {
  "actual_assertions": {
    "assert_name_valid": true,
    "check_length": true
  },
  "actual_outputs": {
    "result": {
      "greeting": "Welcome, BERAT!",
      "valid": true
    }
  },
  "assertions": [
    {
      "actual": true,
      "expected": true,
      "id": "assert_name_valid",
      "match_state": "MATCH"
    },
    {
      "actual": true,
      "expected": true,
      "id": "check_length",
      "match_state": "MATCH"
    }
  ],
  "baseline": null,
  "diagnostics": [],
  "execution": {
    "actual_error_code": null,
    "expected_error_code": null,
    "expected_error_occurred": false,
    "success": true,
    "total_nodes_executed": 4
  },
  "fixture": {
    "display_name": "Trim and Uppercase User Fixture",
    "id": "fixture-trim-upper",
    "name": "Trim and Uppercase User Fixture"
  },
  "fixture_id": "fixture-trim-upper",
  "outputs": [
    {
      "actual": {
        "greeting": "Welcome, BERAT!",
        "valid": true
      },
      "expected": {
        "greeting": "Welcome, BERAT!",
        "valid": true
      },
      "id": "result",
      "match_state": "MATCH"
    }
  ],
  "overall_status": "PASS",
  "status": "PASSED",
  "status_presentation": {
    "badge": "success",
    "label": "PASS",
    "passed": true,
    "status": "PASS"
  },
  "success": true,
  "traces": [
    {
      "kind": "transform",
      "node_id": "trim_user",
      "output": "berat",
      "resolved_inputs": {
        "value": "  berat  "
      },
      "step": 0
    },
    {
      "kind": "transform",
      "node_id": "uppercase_user",
      "output": "BERAT",
      "resolved_inputs": {
        "value": "berat"
      },
      "step": 1
    },
    {
      "kind": "assert",
      "node_id": "check_length",
      "output": true,
      "resolved_inputs": {
        "value": "BERAT"
      },
      "step": 2
    },
    {
      "kind": "construct",
      "node_id": "package_result",
      "output": {
        "greeting": "Welcome, BERAT!",
        "valid": true
      },
      "resolved_inputs": {
        "name": "BERAT"
      },
      "step": 3
    }
  ],
  "validation": {
    "error_count": 0,
    "fixture_valid": true,
    "warning_count": 0,
    "workflow_valid": true
  },
  "workflow": {
    "display_name": "user_transform_flow",
    "fingerprint": "4e8da90561979d43a52e5631910e4b610566c7161f1cea5ff792c6b1b2eef21e",
    "name": "user_transform_flow"
  },
  "workflow_fingerprint": "4e8da90561979d43a52e5631910e4b610566c7161f1cea5ff792c6b1b2eef21e"
};

export const mockOutputMismatchReport: DeveloperReport = {
  "actual_assertions": {
    "assert_name_valid": true,
    "check_length": true
  },
  "actual_outputs": {
    "result": {
      "greeting": "Welcome, BERAT!",
      "valid": true
    }
  },
  "assertions": [
    {
      "actual": true,
      "expected": true,
      "id": "assert_name_valid",
      "match_state": "MATCH"
    },
    {
      "actual": true,
      "expected": true,
      "id": "check_length",
      "match_state": "MATCH"
    }
  ],
  "baseline": null,
  "diagnostics": [
    {
      "category": "output",
      "code": "WYS852",
      "hint": null,
      "location": null,
      "message": "output mismatch for 'result': expected {'greeting': 'Welcome, BERATCAN!', 'valid': True}, got {'greeting': 'Welcome, BERAT!', 'valid': True}",
      "node_id": null,
      "path": "/outputs/result",
      "severity": "error"
    }
  ],
  "execution": {
    "actual_error_code": null,
    "expected_error_code": null,
    "expected_error_occurred": false,
    "success": false,
    "total_nodes_executed": 4
  },
  "fixture": {
    "display_name": "Strict Greeting Expectation",
    "id": "fixture-mismatch",
    "name": "Strict Greeting Expectation"
  },
  "fixture_id": "fixture-mismatch",
  "outputs": [
    {
      "actual": {
        "greeting": "Welcome, BERAT!",
        "valid": true
      },
      "expected": {
        "greeting": "Welcome, BERATCAN!",
        "valid": true
      },
      "id": "result",
      "match_state": "MISMATCH"
    }
  ],
  "overall_status": "FAIL",
  "status": "OUTPUT_MISMATCH",
  "status_presentation": {
    "badge": "failure",
    "label": "OUTPUT MISMATCH",
    "passed": false,
    "status": "OUTPUT_MISMATCH"
  },
  "success": false,
  "traces": [
    {
      "kind": "transform",
      "node_id": "trim_user",
      "output": "berat",
      "resolved_inputs": {
        "value": "  berat  "
      },
      "step": 0
    },
    {
      "kind": "transform",
      "node_id": "uppercase_user",
      "output": "BERAT",
      "resolved_inputs": {
        "value": "berat"
      },
      "step": 1
    },
    {
      "kind": "assert",
      "node_id": "check_length",
      "output": true,
      "resolved_inputs": {
        "value": "BERAT"
      },
      "step": 2
    },
    {
      "kind": "construct",
      "node_id": "package_result",
      "output": {
        "greeting": "Welcome, BERAT!",
        "valid": true
      },
      "resolved_inputs": {
        "name": "BERAT"
      },
      "step": 3
    }
  ],
  "validation": {
    "error_count": 1,
    "fixture_valid": true,
    "warning_count": 0,
    "workflow_valid": true
  },
  "workflow": {
    "display_name": "user_transform_flow",
    "fingerprint": "4e8da90561979d43a52e5631910e4b610566c7161f1cea5ff792c6b1b2eef21e",
    "name": "user_transform_flow"
  },
  "workflow_fingerprint": "4e8da90561979d43a52e5631910e4b610566c7161f1cea5ff792c6b1b2eef21e"
};

export const mockRegressionReport: DeveloperReport = {
  "actual_assertions": {
    "assert_name_valid": true,
    "check_length": true
  },
  "actual_outputs": {
    "result": {
      "greeting": "Welcome, BERATCAN!",
      "valid": true
    }
  },
  "assertions": [
    {
      "actual": true,
      "expected": true,
      "id": "assert_name_valid",
      "match_state": "MATCH"
    },
    {
      "actual": true,
      "expected": true,
      "id": "check_length",
      "match_state": "MATCH"
    }
  ],
  "baseline": {
    "assertion_diffs": [
      {
        "actual": true,
        "category": "assertion",
        "expected": true,
        "kind": "MATCH",
        "message": "Assertion 'assert_name_valid' match",
        "name": "assert_name_valid"
      },
      {
        "actual": true,
        "category": "assertion",
        "expected": true,
        "kind": "MATCH",
        "message": "Assertion 'check_length' match",
        "name": "check_length"
      }
    ],
    "assertions_changed": false,
    "diff_entries": [
      {
        "actual": "fixture-mismatch",
        "category": "fixture",
        "expected": "fixture-trim-upper",
        "kind": "CHANGED",
        "message": "Fixture ID changed: expected 'fixture-trim-upper', got 'fixture-mismatch'",
        "name": "fixture_id"
      },
      {
        "actual": {
          "greeting": "Welcome, BERATCAN!",
          "valid": true
        },
        "category": "output",
        "expected": {
          "greeting": "Welcome, BERAT!",
          "valid": true
        },
        "kind": "CHANGED",
        "message": "Output 'result' changed",
        "name": "result"
      },
      {
        "actual": "d15138f4fd95aaab67f4763e188a610e03d7c51b339b986e54c340abbe3fde0a",
        "category": "workflow",
        "expected": "4e8da90561979d43a52e5631910e4b610566c7161f1cea5ff792c6b1b2eef21e",
        "kind": "CHANGED",
        "message": "Workflow fingerprint changed",
        "name": "workflow_fingerprint"
      }
    ],
    "expected_error_actual": null,
    "expected_error_changed": false,
    "expected_error_expected": null,
    "fixture_actual": "fixture-mismatch",
    "fixture_changed": true,
    "fixture_expected": "fixture-trim-upper",
    "matches": false,
    "output_diffs": [
      {
        "actual": {
          "greeting": "Welcome, BERATCAN!",
          "valid": true
        },
        "category": "output",
        "expected": {
          "greeting": "Welcome, BERAT!",
          "valid": true
        },
        "kind": "CHANGED",
        "message": "Output 'result' changed",
        "name": "result"
      }
    ],
    "outputs_changed": true,
    "reasons": [
      "Workflow fingerprint changed",
      "Fixture ID changed: expected 'fixture-trim-upper', got 'fixture-mismatch'",
      "Output 'result' changed"
    ],
    "status": "REGRESSION",
    "status_actual": "PASSED",
    "status_changed": false,
    "status_expected": "PASSED",
    "workflow_actual": "d15138f4fd95aaab67f4763e188a610e03d7c51b339b986e54c340abbe3fde0a",
    "workflow_changed": true,
    "workflow_expected": "4e8da90561979d43a52e5631910e4b610566c7161f1cea5ff792c6b1b2eef21e"
  },
  "diagnostics": [],
  "execution": {
    "actual_error_code": null,
    "expected_error_code": null,
    "expected_error_occurred": false,
    "success": true,
    "total_nodes_executed": 4
  },
  "fixture": {
    "display_name": "Strict Greeting Expectation",
    "id": "fixture-mismatch",
    "name": "Strict Greeting Expectation"
  },
  "fixture_id": "fixture-mismatch",
  "outputs": [
    {
      "actual": {
        "greeting": "Welcome, BERATCAN!",
        "valid": true
      },
      "expected": {
        "greeting": "Welcome, BERATCAN!",
        "valid": true
      },
      "id": "result",
      "match_state": "MATCH"
    }
  ],
  "overall_status": "FAIL",
  "status": "REGRESSION",
  "status_presentation": {
    "badge": "failure",
    "label": "REGRESSION",
    "passed": false,
    "status": "REGRESSION"
  },
  "success": false,
  "traces": [
    {
      "kind": "transform",
      "node_id": "trim_user",
      "output": "berat",
      "resolved_inputs": {
        "value": "  berat  "
      },
      "step": 0
    },
    {
      "kind": "transform",
      "node_id": "uppercase_user",
      "output": "BERAT",
      "resolved_inputs": {
        "value": "berat"
      },
      "step": 1
    },
    {
      "kind": "assert",
      "node_id": "check_length",
      "output": true,
      "resolved_inputs": {
        "value": "BERAT"
      },
      "step": 2
    },
    {
      "kind": "construct",
      "node_id": "package_result",
      "output": {
        "greeting": "Welcome, BERATCAN!",
        "valid": true
      },
      "resolved_inputs": {
        "name": "BERAT"
      },
      "step": 3
    }
  ],
  "validation": {
    "error_count": 0,
    "fixture_valid": true,
    "warning_count": 0,
    "workflow_valid": true
  },
  "workflow": {
    "display_name": "user_transform_flow",
    "fingerprint": "d15138f4fd95aaab67f4763e188a610e03d7c51b339b986e54c340abbe3fde0a",
    "name": "user_transform_flow"
  },
  "workflow_fingerprint": "d15138f4fd95aaab67f4763e188a610e03d7c51b339b986e54c340abbe3fde0a"
};

export const mockRuntimeErrorReport: DeveloperReport = {
  "actual_assertions": {},
  "actual_outputs": {},
  "assertions": [],
  "baseline": null,
  "diagnostics": [
    {
      "category": "runtime",
      "code": "WYS801",
      "hint": null,
      "location": null,
      "message": "JSON Pointer segment 'contacts' not found in object (path: '/user/contacts/email') in node 'get_email'",
      "node_id": "get_email",
      "path": "/nodes/get_email",
      "severity": "error"
    }
  ],
  "execution": {
    "actual_error_code": "WYS801",
    "expected_error_code": null,
    "expected_error_occurred": false,
    "success": false,
    "total_nodes_executed": 0
  },
  "fixture": {
    "display_name": "Empty User Object",
    "id": "fixture-missing-email",
    "name": "Empty User Object"
  },
  "fixture_id": "fixture-missing-email",
  "outputs": [],
  "overall_status": "FAIL",
  "status": "RUNTIME_ERROR",
  "status_presentation": {
    "badge": "error",
    "label": "RUNTIME ERROR",
    "passed": false,
    "status": "RUNTIME_ERROR"
  },
  "success": false,
  "traces": [],
  "validation": {
    "error_count": 1,
    "fixture_valid": true,
    "warning_count": 0,
    "workflow_valid": true
  },
  "workflow": {
    "display_name": "data_extractor",
    "fingerprint": "02b8e174b0afd58c07242dd50bbbff0f87d6f5a83a0cc17851cd32e53540c3a5",
    "name": "data_extractor"
  },
  "workflow_fingerprint": "02b8e174b0afd58c07242dd50bbbff0f87d6f5a83a0cc17851cd32e53540c3a5"
};

export interface MockScenario {
  id: string;
  name: string;
  description: string;
  report: DeveloperReport;
}

export const mockScenarios: MockScenario[] = [
  {
    id: 'successful-verification',
    name: 'Successful Verification (PASS)',
    description: 'Deterministic execution of user_transform_flow against happy-path fixture. All assertions and outputs match.',
    report: mockSuccessfulReport,
  },
  {
    id: 'failed-output',
    name: 'Output Mismatch Failure (FAIL)',
    description: 'Workflow produced "Welcome, BERAT!" but fixture strictly expected "Welcome, BERATCAN!".',
    report: mockOutputMismatchReport,
  },
  {
    id: 'regression-result',
    name: 'Regression Detected (REGRESSION)',
    description: 'Workflow proposal changed greeting output contract and fingerprint. Baseline diff flags output regression while assertions remain unchanged.',
    report: mockRegressionReport,
  },
  {
    id: 'runtime-error',
    name: 'Runtime Pointer Error (ERROR)',
    description: 'Select node failed at runtime due to missing JSON pointer segment in fixture input.',
    report: mockRuntimeErrorReport,
  },
];

export function getScenarioById(id: string): MockScenario | undefined {
  return mockScenarios.find((s) => s.id === id);
}
