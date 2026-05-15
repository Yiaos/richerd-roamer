from pathlib import Path

from roamerd.compat.legacy_config import load_config
from roamerd.config.loader import load_config as load_roamerd_config


def test_current_config_migrates_key_values() -> None:
    config = load_config()
    assert config.capabilities.motion.driver == "ros2_nav"
    assert config.capabilities.hearing.vad.silero.threshold == 0.1
    assert config.capabilities.hearing.session.max_turns == 1
    assert config.bridges.control.socket == "/run/roamer/roamer.sock"
    assert config.capabilities.speech.bluetooth.speaker_mac == "B8:5C:EE:89:00:BE"
    assert config.policy.local_voice.pre_roll_sec == 1.0
    assert config.policy.local_voice.followup_timeout_sec == 3.0
    assert config.policy.local_voice.continuous_followup_enabled is True
    assert config.policy.local_voice.max_followup_turns == 3
    assert "阳台" in config.world_model.places


def test_roamerd_yaml_preserves_migrated_named_points() -> None:
    config = load_roamerd_config(Path("config/roamerd.yaml"))
    place = config.world_model.places["阳台"]
    assert place.pose.x == 2082
    assert place.pose.y == 2377
    assert place.pose.angle == 111
