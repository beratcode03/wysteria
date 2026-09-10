from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()


def test_validate_cli_success(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text(
        """ir_version: 1
name: sample
metadata: {}
inputs: {}
nodes:
  - id: value
    kind: constant
    inputs: {}
    config: {value: hello}
    output_type: string
edges: []
capabilities: []
assertions: []
outputs:
  result: {source: {node: value}, type: string}
""",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0
    assert "PASS" in result.stdout


def test_validate_cli_json_failure(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text("ir_version: 1\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path), "--format", "json"])
    assert result.exit_code == 1
    assert '"valid": false' in result.stdout


def test_validate_cli_policy_block(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text(
        """ir_version: 1
name: sample
metadata: {}
inputs: {}
nodes: [{id: value, kind: constant, inputs: {}, config: {value: 1}, output_type: integer}]
edges: []
capabilities: [network.http]
assertions: []
outputs: {result: {source: {node: value}, type: integer}}
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["validate", str(path)]).exit_code == 2


def test_schema_and_doctor():
    assert runner.invoke(app, ["schema", "--ir-version", "1"]).exit_code == 0
    assert runner.invoke(app, ["doctor"]).exit_code == 0
