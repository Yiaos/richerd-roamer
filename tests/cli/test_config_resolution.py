"""CLI config resolution tests."""

from pathlib import Path

from click.testing import CliRunner

from roamer.cli.main import main


def _stub_runtime(monkeypatch, captured: dict) -> None:
    monkeypatch.setattr("roamer.cli.main.load_config", lambda path: captured.setdefault("path", path) or {})
    monkeypatch.setattr("roamer.cli.main._ensure_perception_plugin_registered", lambda _config: None)
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: {"ok": True, "action": action_name},
    )


def test_main_uses_repo_default_config_when_exists(monkeypatch, tmp_path: Path) -> None:
    default_config = tmp_path / "config.yaml"
    default_config.write_text("motion:\n  arrival_tolerance: 123\n", encoding="utf-8")

    captured: dict = {}
    _stub_runtime(monkeypatch, captured)
    monkeypatch.setattr("roamer.cli.main._default_repo_config_path", lambda: default_config)

    runner = CliRunner()
    result = runner.invoke(main, ["sense"])

    assert result.exit_code == 0
    assert captured["path"] == default_config


def test_main_uses_explicit_config_over_repo_default(monkeypatch, tmp_path: Path) -> None:
    default_config = tmp_path / "config.yaml"
    default_config.write_text("motion:\n  arrival_tolerance: 123\n", encoding="utf-8")

    explicit_config = tmp_path / "explicit.yaml"
    explicit_config.write_text("motion:\n  arrival_tolerance: 999\n", encoding="utf-8")

    captured: dict = {}
    _stub_runtime(monkeypatch, captured)
    monkeypatch.setattr("roamer.cli.main._default_repo_config_path", lambda: default_config)

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(explicit_config), "sense"])

    assert result.exit_code == 0
    assert captured["path"] == explicit_config


def test_main_does_not_fallback_to_home_config_when_repo_default_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict = {}
    _stub_runtime(monkeypatch, captured)
    monkeypatch.setattr("roamer.cli.main._default_repo_config_path", lambda: tmp_path / "missing.yaml")

    runner = CliRunner()
    result = runner.invoke(main, ["sense"])

    assert result.exit_code == 0
    assert captured["path"] is None
