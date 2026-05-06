"""CLI tests for SU-03T wake command."""

import json
from unittest.mock import patch

from click.testing import CliRunner

from roamer.cli.main import main


def test_wake_cli_dispatches_action() -> None:
    with patch("roamer.cli.main.run_action", return_value={"ok": True, "completed": True}) as run:
        result = CliRunner().invoke(main, ["wake", "--once", "--timeout", "2", "--no-sound"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "wake"
    run.assert_called_once_with("wake", once=True, timeout=2.0, no_sound=True)
