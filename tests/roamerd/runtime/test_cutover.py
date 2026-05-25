import subprocess
import sys
from pathlib import Path

import yaml


def test_dry_run_prints_driver_plan_without_starting_runtime() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "roamerd", "--config", "config/roamerd.yaml", "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "dry-run ok" in result.stdout
    assert "motion=mock_ros2_nav" in result.stdout


def test_pi_config_and_systemd_unit_define_roamerd_cutover() -> None:
    config = yaml.safe_load(Path("config/roamerd-pi.yaml").read_text(encoding="utf-8"))
    unit = Path("deploy/roamerd.service").read_text(encoding="utf-8")
    preflight = Path("scripts/roamerd-preflight.sh").read_text(encoding="utf-8")
    cutover = Path("scripts/phase-e-cutover.sh").read_text(encoding="utf-8")

    assert config["capabilities"]["motion"]["driver"] == "ros2_nav"
    assert "python -m roamerd --config" in unit
    assert "Restart=always" in unit
    assert Path("scripts/roamerd-preflight.sh").stat().st_mode & 0o111
    assert Path("scripts/phase-e-cutover.sh").stat().st_mode & 0o111
    assert "systemctl --user is-active roamer-serve.service" in preflight
    assert "systemctl --user is-active roamer-wake.service" in preflight
    assert "lsof -t /run/roamer/roamer.sock" in preflight
    assert "roamer ping" in preflight
    assert "scripts/roamerd-preflight.sh" in cutover
    assert "roamer ping" in cutover


def test_roamerd_does_not_import_legacy_roamer_orchestration() -> None:
    for path in Path("src/roamerd").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "src.roamer" not in text
        assert "import roamer" not in text
