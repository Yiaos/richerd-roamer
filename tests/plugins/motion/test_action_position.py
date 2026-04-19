"""Tests for motion.position action."""

from roamer.plugins.motion.actions.position import MotionPositionAction


class _Driver:
    def get_position(self):
        return {"ok": True, "x": 1, "y": 2, "angle": 3}


def test_motion_position_action_uses_driver_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.position.ValetudoMotionDriver",
        lambda cfg: _Driver(),
    )

    action = MotionPositionAction(config={"valetudo": {}})
    result = action.run()

    assert result == {"ok": True, "x": 1, "y": 2, "angle": 3}
