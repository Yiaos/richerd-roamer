"""Tests for roamer init CLI command."""

from click.testing import CliRunner

from roamer.cli.main import main


def test_init_command_emits_structured_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: {
            "ok": True,
            "initialized": True,
            "steps": [],
        },
    )

    runner = CliRunner()
    result = runner.invoke(main, ["init"])

    assert result.exit_code == 0
    assert '"command": "init"' in result.output
    assert '"initialized": true' in result.output
