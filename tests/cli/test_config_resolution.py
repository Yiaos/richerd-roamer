"""CLI and platform config resolution tests."""

from pathlib import Path

from click.testing import CliRunner

from roamer.cli.main import main
from roamer.platform.config import load_config, resolve_config_path


def _stub_runtime(monkeypatch, captured: dict) -> None:
    def capture_config_path(path):
        captured.setdefault("path", path)
        return {}

    monkeypatch.setattr("roamer.cli.main.load_config", capture_config_path)
    monkeypatch.setattr(
        "roamer.cli.main._ensure_perception_plugin_registered",
        lambda _config: None,
    )
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: {"ok": True, "action": action_name},
    )


def test_resolve_config_path_uses_repo_default(monkeypatch, tmp_path: Path) -> None:
    repo_config = tmp_path / "config.yaml"
    repo_config.write_text("motion:\n  arrival_tolerance: 123\n", encoding="utf-8")

    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr("roamer.platform.config.default_repo_config_path", lambda: repo_config)

    assert resolve_config_path(None) == repo_config


def test_resolve_config_path_uses_env_override(monkeypatch, tmp_path: Path) -> None:
    env_config = tmp_path / "env.yaml"
    monkeypatch.setenv("ROAMER_CONFIG", str(env_config))
    monkeypatch.setattr(
        "roamer.platform.config.default_repo_config_path",
        lambda: tmp_path / "repo.yaml",
    )

    assert resolve_config_path(None) == env_config


def test_load_config_uses_resolved_repo_default(monkeypatch, tmp_path: Path) -> None:
    repo_config = tmp_path / "config.yaml"
    repo_config.write_text(
        "converse:\n  discord:\n    enabled: true\n    channel_id: 'abc'\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr("roamer.platform.config.default_repo_config_path", lambda: repo_config)

    config = load_config()

    assert config["converse"]["discord"]["enabled"] is True
    assert config["converse"]["discord"]["channel_id"] == "abc"


def test_main_uses_shared_resolved_config(monkeypatch, tmp_path: Path) -> None:
    repo_config = tmp_path / "config.yaml"
    repo_config.write_text("init:\n  configure_proxy_on_startup: true\n", encoding="utf-8")

    captured: dict = {}
    _stub_runtime(monkeypatch, captured)
    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr("roamer.platform.config.default_repo_config_path", lambda: repo_config)

    runner = CliRunner()
    result = runner.invoke(main, ["sense"])

    assert result.exit_code == 0
    assert captured["path"] is None


def test_main_uses_explicit_config_over_defaults(monkeypatch, tmp_path: Path) -> None:
    explicit_config = tmp_path / "explicit.yaml"
    explicit_config.write_text("motion:\n  arrival_tolerance: 999\n", encoding="utf-8")

    captured: dict = {}
    _stub_runtime(monkeypatch, captured)
    monkeypatch.setattr(
        "roamer.platform.config.default_repo_config_path",
        lambda: tmp_path / "repo.yaml",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(explicit_config), "sense"])

    assert result.exit_code == 0
    assert captured["path"] == explicit_config


def test_main_uses_no_config_when_defaults_missing(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}
    _stub_runtime(monkeypatch, captured)
    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr(
        "roamer.platform.config.default_repo_config_path",
        lambda: tmp_path / "missing-repo.yaml",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["sense"])

    assert result.exit_code == 0
    assert captured["path"] is None


def test_load_config_merges_serve_defaults(monkeypatch, tmp_path: Path) -> None:
    repo_config = tmp_path / "config.yaml"
    repo_config.write_text(
        "serve:\n  fallback_to_cli: false\nconverse:\n  endpoint:\n    silence_sec: 1.5\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("ROAMER_CONFIG", raising=False)
    monkeypatch.setattr("roamer.platform.config.default_repo_config_path", lambda: repo_config)

    config = load_config()

    assert config["serve"]["fallback_to_cli"] is False
    assert config["serve"]["enabled"] is True
    assert config["converse"]["endpoint"]["silence_sec"] == 1.5
    assert config["converse"]["endpoint"]["mode"] == "fixed_recording"
