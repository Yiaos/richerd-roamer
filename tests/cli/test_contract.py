"""Contract regression tests for CLI egress behavior."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from roamer.cli.main import main
from roamer.platform.contract import SCHEMA_VERSION, ExitCategory
from roamer.platform.output import error as output_error
from roamer.plugins.interaction.capabilities.speak import SpeakCapability


def test_json_mode_failure_exits_nonzero_and_has_contract_fields():
    """JSON failure should emit deterministic contract payload and mapped non-zero exit."""
    runner = CliRunner()

    with patch("roamer.cli.main.run_action") as mock_run_action:
        mock_run_action.return_value = output_error("audio_record_failed", "record failed")

        result = runner.invoke(main, ["watch"])

    assert result.exit_code == ExitCategory.RUNTIME.value
    payload = json.loads(result.output.strip())
    assert payload["ok"] is False
    assert payload["error"] == "audio_record_failed"
    assert payload["error_code"] == "audio.record.command_failed"
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["command"] == "watch"


def test_text_only_failure_writes_stderr_and_nonzero_exit():
    """listen --text-only failure should print JSON to stderr and exit by mapped category."""
    runner = CliRunner()

    with patch("roamer.plugins.interaction.capabilities.listen.ListenCapability") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.listen.return_value = {
            "ok": False,
            "error": "missing_binary",
            "message": "arecord not found",
            "error_code": "dependency.audio.arecord_missing",
        }
        mock_cap_cls.return_value = mock_cap

        result = runner.invoke(main, ["listen", "--text-only"])

    assert result.exit_code == ExitCategory.DEPENDENCY.value
    payload = json.loads(result.stderr.strip())
    assert payload["ok"] is False
    assert payload["command"] == "listen"
    assert payload["schema_version"] == SCHEMA_VERSION


def test_success_payload_contains_command_and_schema_version():
    """Successful JSON responses should include command and schema metadata."""
    runner = CliRunner()

    with patch("roamer.cli.main.run_action") as mock_run_action:
        mock_run_action.return_value = {
            "ok": True,
            "hostname": "roamer-test",
        }

        result = runner.invoke(main, ["sense"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["ok"] is True
    assert payload["command"] == "sense"
    assert payload["schema_version"] == SCHEMA_VERSION


def test_speak_partial_success_when_playback_fails():
    """Speak should expose partial success when synthesis succeeds but playback fails."""
    with patch(
        "roamer.plugins.interaction.capabilities.speak.get_driver_name",
        return_value="edge",
    ):
        with patch(
            "roamer.plugins.interaction.capabilities.speak.get_driver_config",
            return_value={},
        ):
            with patch(
                "roamer.plugins.interaction.capabilities.speak.get_driver"
            ) as mock_get_driver:
                with patch(
                    "roamer.plugins.interaction.capabilities.speak.AudioCapability"
                ) as mock_audio_cls:
                    mock_tts = MagicMock()
                    mock_tts.synthesize.return_value = {
                        "ok": True,
                        "duration_sec": 1.2,
                    }
                    mock_get_driver.return_value = mock_tts

                    mock_audio = MagicMock()
                    mock_audio.play.return_value = {
                        "ok": False,
                        "error": "audio_play_failed",
                        "error_code": "audio.play.command_failed",
                        "message": "speaker disconnected",
                    }
                    mock_audio_cls.return_value = mock_audio

                    capability = SpeakCapability({"drivers": {"tts": "edge"}})
                    with patch.object(capability, "_ensure_bluetooth_connected", return_value=True):
                        result = capability.speak("测试语音", play=True)

    assert result["ok"] is True
    assert result["played"] is False
    assert result["partial"] is True
    assert result["warning_code"] == "audio.play.command_failed"
    assert result["warning_message"] == "speaker disconnected"
