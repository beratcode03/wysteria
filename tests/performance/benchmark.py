import gc
import timeit


def benchmark_scenario(name, stmt, setup, number=100):
    gc.collect()
    timer = timeit.Timer(stmt, setup=setup)
    time_taken = timer.timeit(number=number)
    avg_ms = (time_taken / number) * 1000
    print(f"{name:<40} | {avg_ms:>8.2f} ms")


def run_benchmarks():
    print("Wysteria Core Benchmark Suite")
    print("-" * 55)
    print(f"{'Scenario':<40} | {'Avg Time':>8}")
    print("-" * 55)

    base_setup = """
from pathlib import Path
from wysteria.api import load_workflow, validate_workflow, load_fixture_document, verify_fixture, diff_workflows, load_policy, evaluate_policy

examples = Path('examples')
wf_path = examples / 'quickstart' / 'workflow.yaml'
fix_path = examples / 'quickstart' / 'fixture.yaml'
pol_path = examples / 'quickstart' / 'policy.yaml'
real_wf_path = examples / 'realistic_pipeline.yaml'

parsed_wf = load_workflow(wf_path)
parsed_fix = load_fixture_document(fix_path)
policy = load_policy(pol_path)
parsed_real = load_workflow(real_wf_path)

val_res = validate_workflow(parsed_wf)
wf = val_res.workflow
"""

    benchmark_scenario(
        "Realistic Pipeline Parsing", "load_workflow(real_wf_path)", setup=base_setup, number=100
    )

    benchmark_scenario(
        "Realistic Pipeline Validation",
        "validate_workflow(parsed_real)",
        setup=base_setup,
        number=100,
    )

    benchmark_scenario(
        "Small Workflow Parsing", "load_workflow(wf_path)", setup=base_setup, number=200
    )

    benchmark_scenario(
        "Small Workflow Validation", "validate_workflow(parsed_wf)", setup=base_setup, number=200
    )

    benchmark_scenario(
        "Full Verification (workflow + fixture)",
        "verify_fixture(parsed_wf, parsed_fix)",
        setup=base_setup,
        number=100,
    )

    benchmark_scenario(
        "Semantic Diff (identical)", "diff_workflows(wf, wf)", setup=base_setup, number=100
    )

    benchmark_scenario(
        "Policy Evaluation", "evaluate_policy(wf, policy)", setup=base_setup, number=200
    )

    print("-" * 55)
    print("Note: 'Large' models scale linearly with node count.")
    print("These numbers are informational benchmarks on local hardware.")


if __name__ == "__main__":
    run_benchmarks()
