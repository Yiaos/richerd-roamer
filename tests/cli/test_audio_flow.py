"""Tests for audio two-command CLI flow (listen + speak)."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from roamer.cli.main import main
from roamer.platform.contract import ErrorCode


class TestCliAudioFlow:
    """Tests for listen/speak command composition behavior."""

    def test_listen_default_json_output(self):
        """listen should keep default JSON output for backward compatibility."""
        runner = CliRunner()

        with patch(
            "roamer.plugins.interaction.capabilities.listen.ListenCapability"
        ) as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.listen.return_value = {
                "ok": True,
                "text": "你好",
                "confidence": 0.95,
                "duration_sec": 1.2,
            }
            mock_cap_cls.return_value = mock_cap

            result = runner.invoke(main, ["listen", "--timeout", "3"])

        assert result.exit_code == 0
        payload = json.loads(result.output.strip())
        assert payload["ok"] is True
        assert payload["text"] == "你好"
        mock_cap.listen.assert_called_once_with(timeout=3.0, save_audio=None, debug=False)

    def test_listen_text_only_output(self):
        """listen --text-only should print plain text only."""
        runner = CliRunner()

        with patch(
            "roamer.plugins.interaction.capabilities.listen.ListenCapability"
        ) as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.listen.return_value = {
                "ok": True,
                "text": "测试文本",
                "confidence": 0.91,
            }
            mock_cap_cls.return_value = mock_cap

            result = runner.invoke(main, ["listen", "--text-only"])

        assert result.exit_code == 0
        assert result.output == "测试文本\n"

    def test_speak_positional_text_mode(self):
        """speak positional mode should remain supported."""
        runner = CliRunner()

        with patch("roamer.plugins.interaction.capabilities.speak.SpeakCapability") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.speak.return_value = {
                "ok": True,
                "text": "你好，Richer",
                "duration_sec": 1.0,
                "played": True,
            }
            mock_cap_cls.return_value = mock_cap

            result = runner.invoke(main, ["speak", "你好，Richer"])

        assert result.exit_code == 0
        payload = json.loads(result.output.strip())
        assert payload["ok"] is True
        assert payload["text"] == "你好，Richer"
        mock_cap.speak.assert_called_once_with(
            "你好，Richer",
            save_path=None,
            play=True,
            style=None,
        )

    def test_speak_stdin_with_prefix(self):
        """speak --stdin should read input and apply optional prefix."""
        runner = CliRunner()

        with patch("roamer.plugins.interaction.capabilities.speak.SpeakCapability") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.speak.return_value = {
                "ok": True,
                "text": "我听到的是：测试",
                "duration_sec": 1.0,
                "played": True,
            }
            mock_cap_cls.return_value = mock_cap

            result = runner.invoke(
                main,
                ["speak", "--stdin", "--prefix", "我听到的是："],
                input="测试\n",
            )

        assert result.exit_code == 0
        payload = json.loads(result.output.strip())
        assert payload["ok"] is True
        mock_cap.speak.assert_called_once_with(
            "我听到的是：测试",
            save_path=None,
            play=True,
            style=None,
        )

    def test_pipeline_style_listen_to_speak(self):
        """Text output from listen should compose cleanly into speak --stdin."""
        runner = CliRunner()

        with patch(
            "roamer.plugins.interaction.capabilities.listen.ListenCapability"
        ) as mock_listen_cls:
            mock_listen = MagicMock()
            mock_listen.listen.return_value = {"ok": True, "text": "管线测试"}
            mock_listen_cls.return_value = mock_listen

            listen_result = runner.invoke(main, ["listen", "--text-only"])

        assert listen_result.exit_code == 0
        assert listen_result.output == "管线测试\n"

        with patch(
            "roamer.plugins.interaction.capabilities.speak.SpeakCapability"
        ) as mock_speak_cls:
            mock_speak = MagicMock()
            mock_speak.speak.return_value = {
                "ok": True,
                "text": "我听到的是：管线测试",
                "duration_sec": 1.0,
                "played": True,
            }
            mock_speak_cls.return_value = mock_speak

            speak_result = runner.invoke(
                main,
                ["speak", "--stdin", "--prefix", "我听到的是："],
                input=listen_result.output,
            )

        assert speak_result.exit_code == 0
        payload = json.loads(speak_result.output.strip())
        assert payload["ok"] is True
        mock_speak.speak.assert_called_once_with(
            "我听到的是：管线测试",
            save_path=None,
            play=True,
            style=None,
        )

    def test_listen_failure_json_keeps_legacy_error_and_canonical_error_code(self):
        """listen failure JSON should include canonical error_code and legacy error field."""
        runner = CliRunner()

        with patch(
            "roamer.plugins.interaction.capabilities.listen.ListenCapability"
        ) as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.listen.return_value = {
                "ok": False,
                "error": "vad_no_speech",
                "error_code": ErrorCode.SPEECH_VAD_NO_SPEECH,
                "message": "No speech detected in recording",
            }
            mock_cap_cls.return_value = mock_cap

            result = runner.invoke(main, ["listen", "--timeout", "3"])

        assert result.exit_code != 0
        payload = json.loads(result.output.strip())
        assert payload["ok"] is False
        assert payload["error"] == "vad_no_speech"
        assert payload["error_code"] == ErrorCode.SPEECH_VAD_NO_SPEECH


def test_listen_dispatches_via_registry_run_action():
    """listen command should dispatch through run_action."""
    runner = CliRunner()

    with patch("roamer.cli.main.run_action") as mock_run_action:
        mock_run_action.return_value = {
            "ok": True,
            "text": "hello",
            "confidence": 0.8,
        }

        result = runner.invoke(main, ["listen", "--timeout", "2"])

    assert result.exit_code == 0
    mock_run_action.assert_called_once_with(
        "listen",
        timeout=2.0,
        save_audio=None,
        debug=False,
    )


def test_bt_connect_dispatches_via_registry_run_action():
    """bt connect command should dispatch through run_action."""
    runner = CliRunner()

    with patch("roamer.cli.main.run_action") as mock_run_action:
        mock_run_action.return_value = {"ok": True, "connected": True}

        result = runner.invoke(main, ["bt", "connect", "AA:BB:CC:DD:EE:FF"])

    assert result.exit_code == 0
    mock_run_action.assert_called_once_with("bt.connect", address="AA:BB:CC:DD:EE:FF")
