"""Tests for motion.status action."""

from roamer.plugins.motion.actions.status import MotionStatusAction


class _Driver:
    def get_status(self):
        return {"ok": True, "status": "idle", "battery_percent": 88}


def test_motion_status_action_uses_driver_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.status.ValetudoMotionDriver",
        lambda cfg: _Driver(),
    )

    action = MotionStatusAction(config={"valetudo": {}})
    result = action.run()

    assert result["ok"] is True
    assert result["status"] == "idle"
    assert result["battery_percent"] == 88
