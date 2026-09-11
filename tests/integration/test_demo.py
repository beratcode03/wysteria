import json

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()


def test_demo_smoke_command():
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Wysteria Demo" in result.stdout
    assert "Workflow: quickstart" in result.stdout
    assert "Verification: PASSED" in result.stdout
    assert "Assertions: 3/3" in result.stdout
    assert "Outputs: 2/2" in result.stdout
    assert "Policy: PASS" in result.stdout
    assert "Gate: PASS" in result.stdout


def test_demo_json_output():
    result = runner.invoke(app, ["demo", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "PASSED"
    assert data["gate"]["decision"] == "PASS"
