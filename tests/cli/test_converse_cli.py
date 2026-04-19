"""CLI tests for converse command surface and contract."""

import json

from click.testing import CliRunner

from roamer.cli.main import main


def test_converse_cli_dispatch_and_contract() -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "converse",
            "--no-wakeword",
            "--timeout",
            "4",
            "--no-sound",
            "--max-turns",
            "2",
        ],
    )

    assert result.exit_code in {0, 2, 10, 11, 12}
    payload = json.loads(result.output.strip())
    assert payload["command"] == "converse"
    assert "schema_version" in payload


def test_converse_cli_uses_config_defaults_when_no_flags(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "converse:",
                "  silence_timeout: 3.5",
                "  max_turns: 2",
                "  no_sound_default: true",
                "  wakeword:",
                "    enabled: false",
            ]
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config), "converse"])

    assert result.exit_code in {0, 2, 10, 11, 12}
    payload = json.loads(result.output.strip())
    assert payload["command"] == "converse"
