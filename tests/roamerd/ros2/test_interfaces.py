from pathlib import Path


def test_roamer_ros2_interfaces_are_present() -> None:
    root = Path("ros2_ws/src/roamer_interfaces")

    goto = (root / "action" / "GoTo.action").read_text(encoding="utf-8")
    home = (root / "action" / "Home.action").read_text(encoding="utf-8")
    robot_state = (root / "msg" / "RobotState.msg").read_text(encoding="utf-8")

    assert goto
    assert "success" not in goto
    assert home
    assert "error_code" in (root / "srv" / "Stop.srv").read_text(encoding="utf-8")
    assert (root / "srv" / "GetStatus.srv").exists()
    assert (root / "srv" / "GetPosition.srv").exists()
    assert (root / "srv" / "Locate.srv").exists()
    assert "map_id" in robot_state
    assert "map_hash" in robot_state
    assert (root / "package.xml").exists()
    assert Path("ros2_ws/src/roamer_ros/roamer_ros/mock_nav_node.py").exists()


def test_motion_contract_documents_frozen_semantics() -> None:
    contract = Path("migration/motion-contract.md").read_text(encoding="utf-8")

    for phrase in [
        "coordinate frame",
        "Stop.srv",
        "running-detached",
        "arrival tolerance",
        "map_id",
        "map_hash",
        "stale RobotState",
        "cancel goals -> call stop -> bounded wait",
    ]:
        assert phrase in contract


def test_valetudo_reality_probe_records_hardware_acceptance_gap() -> None:
    probe = Path("migration/valetudo-reality-probe.md").read_text(encoding="utf-8")

    assert "HARDWARE-EXCLUDED" in probe
    assert "/api/v2/robot/state" in probe
