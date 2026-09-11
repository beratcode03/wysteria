import json

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()


def test_demo_smoke_command():
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Wysteria Verification Showcase" in result.stdout
    assert "Scenario 1: Validating Safe Proposal..." in result.stdout
    assert "DECISION: PASS" in result.stdout
    assert "Scenario 2: Validating Malicious Proposal..." in result.stdout
    assert "DECISION: BLOCK" in result.stdout
    assert "WYS453: forbidden capability requested: 'process.execute'" in result.stdout


def test_demo_json_output():
    result = runner.invoke(app, ["demo", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2

    safe_case = data[0]
    assert safe_case["explanation"]["decision"] == "PASS"

    malicious_case = data[1]
    assert malicious_case["explanation"]["decision"] == "BLOCK"
