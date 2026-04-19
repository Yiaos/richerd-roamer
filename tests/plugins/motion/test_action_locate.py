"""Tests for motion.locate action."""

from roamer.plugins.motion.actions.locate import MotionLocateAction


class _Driver:
    def locate(self):
        return {"ok": True, "capability": "LocateCapability", "action": "locate"}


def test_motion_locate_action_uses_driver_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.locate.ValetudoMotionDriver",
        lambda cfg: _Driver(),
    )

    action = MotionLocateAction(config={"valetudo": {}})
    result = action.run()

    assert result["ok"] is True
    assert result["action"] == "locate"
