"""CLI tests for plugin action isolation across interaction commands."""

import json

from click.testing import CliRunner

from roamer.cli.main import main


def test_bt_status_is_not_blocked_by_broken_asr_config(tmp_path) -> None:
    """bt status should not eagerly depend on listen/asr setup."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "drivers:",
                "  asr: missing_asr",
                "  tts: edge",
                "  vad: silero",
                "  audio: alsa",
                "  bluetooth: bluez",
                "  camera: fswebcam",
            ]
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config_path), "bt", "status"])

    # Bluez may fail in CI/dev environments, but it should fail as contract JSON,
    # not as an eager plugin construction traceback.
    assert result.exit_code in {0, 10, 11, 12}
    payload = json.loads(result.output.strip())
    assert payload["command"] == "bt.status"
    assert "error_code" in payload or payload.get("ok") is True
