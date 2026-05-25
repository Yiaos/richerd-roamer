from pathlib import Path

from roamerd.config.loader import load_config
from roamerd.config.schema import RoamerdConfig


def test_default_config_uses_mock_drivers() -> None:
    config = RoamerdConfig()

    assert config.kernel.event_bus.handler_timeout_sec == 5.0
    assert config.policy.local_intents[0].name == "emergency_stop"
    assert config.capabilities.hearing.audio.driver == "mock"
    assert config.capabilities.speech.playback.driver == "mock"
    assert config.capabilities.motion.driver == "mock_ros2_nav"
    assert config.bridges.cognition.driver == "mock"
    assert config.capabilities.hearing.endpoint.mode == "vad_endpoint"
    assert config.logging.dir == "logs"


def test_load_config_deep_merges_and_expands_env(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("ROAMERD_TEST_SOCKET", "/tmp/roamerd.sock")
    override = tmp_path / "roamerd.yaml"
    override.write_text(
        """
bridges:
  control:
    socket: ${ROAMERD_TEST_SOCKET}
capabilities:
  hearing:
    endpoint:
      silence_sec: 0.75
    vad:
      silero:
        threshold: 0.25
logging:
  dir: /tmp/roamerd-logs
""",
        encoding="utf-8",
    )

    config = load_config(override)

    assert config.bridges.control.socket == "/tmp/roamerd.sock"
    assert config.capabilities.hearing.endpoint.silence_sec == 0.75
    assert config.capabilities.hearing.vad.silero.threshold == 0.25
    assert config.capabilities.hearing.audio.driver == "mock"
    assert config.logging.dir == "/tmp/roamerd-logs"


def test_policy_config_can_override_local_intent_catalog() -> None:
    config = RoamerdConfig.model_validate(
        {
            "policy": {
                "local_intents": [
                    {
                        "name": "custom_ping",
                        "action": "time.now",
                        "patterns": ["报时"],
                        "priority": "normal",
                    }
                ]
            }
        }
    )

    assert [intent.name for intent in config.policy.local_intents] == ["custom_ping"]
