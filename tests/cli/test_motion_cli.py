"""CLI tests for motion command group."""

from click.testing import CliRunner

from roamer.cli.main import main


def test_motion_status_emits_structured_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.cli.main.run_action",
        lambda action_name, **kwargs: {
            "ok": True,
            "status": "idle",
            "battery_percent": 66,
        },
    )

    runner = CliRunner()
    result = runner.invoke(main, ["motion", "status"])

    assert result.exit_code == 0
    assert '"command": "motion.status"' in result.output
    assert '"status": "idle"' in result.output


def test_motion_goto_wait_dispatches_run_action(monkeypatch) -> None:
    called = {}

    def _fake_run(action_name, **kwargs):
        called["action_name"] = action_name
        called["kwargs"] = kwargs
        return {"ok": True, "accepted": True, "waiting": True}

    monkeypatch.setattr("roamer.cli.main.run_action", _fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["motion", "goto", "--x", "100", "--y", "200", "--wait"])

    assert result.exit_code == 0
    assert called["action_name"] == "motion.goto"
    assert called["kwargs"] == {"x": 100, "y": 200, "wait": True}
    assert '"command": "motion.goto"' in result.output


def test_motion_goto_point_dispatches_run_action(monkeypatch) -> None:
    called = {}

    def _fake_run(action_name, **kwargs):
        called["action_name"] = action_name
        called["kwargs"] = kwargs
        return {"ok": True, "accepted": True, "waiting": False}

    monkeypatch.setattr("roamer.cli.main.run_action", _fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["motion", "goto", "--point", "阳台"])

    assert result.exit_code == 0
    assert called["action_name"] == "motion.goto"
    assert called["kwargs"] == {"point": "阳台", "wait": False}
    assert '"command": "motion.goto"' in result.output


def test_motion_goto_with_angle_dispatches_run_action(monkeypatch) -> None:
    called = {}

    def _fake_run(action_name, **kwargs):
        called["action_name"] = action_name
        called["kwargs"] = kwargs
        return {"ok": True, "accepted": True, "waiting": False}

    monkeypatch.setattr("roamer.cli.main.run_action", _fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["motion", "goto", "--x", "100", "--y", "200", "--angle", "277"])

    assert result.exit_code == 0
    assert called["action_name"] == "motion.goto"
    assert called["kwargs"] == {"x": 100, "y": 200, "angle": 277, "wait": False}
    assert '"command": "motion.goto"' in result.output


def test_motion_goto_point_with_angle_dispatches_run_action(monkeypatch) -> None:
    called = {}

    def _fake_run(action_name, **kwargs):
        called["action_name"] = action_name
        called["kwargs"] = kwargs
        return {"ok": True, "accepted": True, "waiting": False}

    monkeypatch.setattr("roamer.cli.main.run_action", _fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["motion", "goto", "--point", "阳台", "--angle", "277"])

    assert result.exit_code == 0
    assert called["action_name"] == "motion.goto"
    assert called["kwargs"] == {"point": "阳台", "angle": 277, "wait": False}
    assert '"command": "motion.goto"' in result.output


def test_motion_home_wait_dispatches_run_action(monkeypatch) -> None:
    called = {}

    def _fake_run(action_name, **kwargs):
        called["action_name"] = action_name
        called["kwargs"] = kwargs
        return {"ok": True, "accepted": True, "waiting": True}

    monkeypatch.setattr("roamer.cli.main.run_action", _fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["motion", "home", "--wait"])

    assert result.exit_code == 0
    assert called["action_name"] == "motion.home"
    assert called["kwargs"] == {"wait": True}
    assert '"command": "motion.home"' in result.output


def test_motion_goto_requires_point_or_coordinates() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["motion", "goto"])

    assert result.exit_code == 2
    assert "Must provide --point or both --x and --y" in result.output


def test_motion_goto_rejects_point_with_coordinates() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["motion", "goto", "--point", "阳台", "--x", "100", "--y", "200"])

    assert result.exit_code == 2
    assert "Cannot combine --point with --x/--y" in result.output


def test_motion_status_missing_valetudo_config_returns_contract_error(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "drivers:",
                "  motion: valetudo",
                "valetudo:",
                "  timeout_sec: 8.0",
            ]
        )
    )

    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config), "motion", "status"])

    assert result.exit_code == 2
    assert '"command": "motion.status"' in result.output
    assert '"error_code": "config.invalid"' in result.output
    assert "Traceback" not in result.output
