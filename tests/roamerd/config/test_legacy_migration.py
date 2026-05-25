from pathlib import Path

from roamerd.compat.legacy_config import migrate_legacy_config


def test_legacy_config_migration_maps_current_config() -> None:
    config, report = migrate_legacy_config(Path("config.yaml"))

    assert report.unmapped_leaf_keys == []
    assert config.capabilities.hearing.vad.silero.threshold == 0.1
    assert config.capabilities.hearing.endpoint.max_record_sec == 10.0
    assert config.capabilities.hearing.stt.chunk_duration_sec == 0.1
    assert config.capabilities.hearing.session.max_turns == 1
    assert config.bridges.control.socket == "/run/roamer/roamer.sock"
    assert config.logging.max_bytes == 10485760
    assert config.logging.log_audio_paths is False
    assert config.capabilities.motion.driver == "ros2_nav"
    assert config.ros2.valetudo_bridge.host == "10.0.0.226"
    assert config.world_model.places["阳台"].x == 2082.0
    assert config.runtime.supervisor.startup.proxy_init_script.endswith(
        "scripts/init-roamer-proxy.sh"
    )
    assert "drivers.motion" in report.mapped_keys
    assert "valetudo.http_moved_to_ros2" in report.ignored_keys


def test_legacy_config_migration_reports_unknown_leaf_keys(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.yaml"
    legacy_path.write_text(
        """
drivers:
  audio: alsa
definitely_unknown:
  nested: value
""",
        encoding="utf-8",
    )

    _, report = migrate_legacy_config(legacy_path)

    assert "drivers.audio" in report.mapped_keys
    assert "definitely_unknown.nested" in report.unmapped_leaf_keys
    assert "definitely_unknown.nested" not in report.mapped_keys
