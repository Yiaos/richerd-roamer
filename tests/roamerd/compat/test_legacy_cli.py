import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from roamerd.compat.legacy_cli import LegacyCliError, legacy_request


def test_legacy_cli_maps_sense_and_speak_commands() -> None:
    sense = legacy_request(["sense"])
    speak = legacy_request(["speak", "hello"])

    assert sense.op == "run"
    assert sense.args["action"] == "sense"
    assert speak.args == {
        "action": "speech.speak",
        "resource": "speaker",
        "payload": {"text": "hello"},
    }


@pytest.mark.parametrize(
    ("argv", "op", "args"),
    [
        (["ping"], "ping", {}),
        (["status"], "status", {}),
        (["listen"], "run", {"action": "hearing.listen", "resource": "microphone"}),
        (["watch"], "run", {"action": "watch", "resource": "camera"}),
        (["home"], "run", {"action": "motion.home", "resource": "motion"}),
        (["goto", "1", "2", "90"], "run", {"action": "motion.goto", "resource": "motion"}),
    ],
)
def test_legacy_cli_maps_supported_old_commands(
    argv: list[str],
    op: str,
    args: dict[str, object],
) -> None:
    request = legacy_request(argv)

    assert request.op == op
    for key, value in args.items():
        assert request.args[key] == value


def test_legacy_cli_rejects_unknown_commands_instead_of_falling_back_to_ping() -> None:
    with pytest.raises(LegacyCliError):
        legacy_request(["definitely-unknown"])


def test_roamer_console_script_points_at_roamerd_shim() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["roamer"] == "roamerd.compat.legacy_cli:main"


def test_roamerd_module_accepts_legacy_command_shape() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "roamerd", "sense"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 2
    assert "unrecognized arguments" not in result.stderr


def test_old_roamer_cli_module_is_cut_over_to_shim() -> None:
    text = Path("src/roamer/cli/main.py").read_text(encoding="utf-8")

    assert "from roamerd.compat.legacy_cli import main" in text
    assert "plugin_registry" not in text
    assert "def run_action" not in text
    assert "roamer.platform.runtime" not in text
    assert "RoamerServeRuntime" not in text
    assert "serve_forever" not in text


def test_old_roamer_cli_module_routes_like_roamerd_module() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "roamer.cli.main", "sense"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 69
    assert "control bridge unavailable" in result.stderr


def test_old_roamer_cli_module_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "roamer.cli.main", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
