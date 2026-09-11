from wysteria import (
    Baseline,
    BaselineComparison,
    CIArtifact,
    DeveloperReport,
    Fixture,
    Policy,
    VerificationResult,
    Workflow,
    __version__,
    build_ci_artifact,
    build_developer_report,
    compare_baseline,
    create_baseline,
    diff_workflows,
    evaluate_policy,
    load_baseline,
    load_ci_artifact,
    load_fixture,
    load_policy,
    load_workflow,
    save_ci_artifact,
    validate_fixture,
    validate_workflow,
    verify_fixture,
)


def test_public_api_exports():
    """Ensure that only the intended stable public API is exported from wysteria."""
    assert isinstance(__version__, str)

    # Check that the models are importable classes
    assert isinstance(Baseline, type)
    assert isinstance(BaselineComparison, type)
    assert isinstance(CIArtifact, type)
    assert isinstance(DeveloperReport, type)
    assert isinstance(Fixture, type)
    assert isinstance(Policy, type)
    assert isinstance(VerificationResult, type)
    assert isinstance(Workflow, type)

    # Check that the functions are importable and callable
    assert callable(build_ci_artifact)
    assert callable(build_developer_report)
    assert callable(compare_baseline)
    assert callable(create_baseline)
    assert callable(diff_workflows)
    assert callable(evaluate_policy)
    assert callable(load_baseline)
    assert callable(load_ci_artifact)
    assert callable(load_fixture)
    assert callable(load_policy)
    assert callable(load_workflow)
    assert callable(save_ci_artifact)
    assert callable(validate_fixture)
    assert callable(validate_workflow)
    assert callable(verify_fixture)
