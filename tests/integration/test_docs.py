from pathlib import Path

from wysteria.cli.main import app


def test_command_catalog_is_up_to_date():
    catalog_path = Path("docs/COMMAND_CATALOG.md")
    assert catalog_path.is_file(), "Command catalog must exist"

    content = catalog_path.read_text(encoding="utf-8")

    # Check that all commands are documented
    def extract(typer_app, prefix="wysteria"):
        cmds = []
        for cmd in typer_app.registered_commands:
            name = cmd.name or cmd.callback.__name__
            cmds.append(f"{prefix} {name}".replace("_command", ""))
        for group in typer_app.registered_groups:
            cmds.extend(extract(group.typer_instance, prefix=f"{prefix} {group.name}"))
        return cmds

    commands = extract(app)
    for cmd in commands:
        if cmd.endswith("main"):
            continue
        assert f"### `{cmd}`" in content, (
            f"Command '{cmd}' is missing from COMMAND_CATALOG.md. Update the docs."
        )
