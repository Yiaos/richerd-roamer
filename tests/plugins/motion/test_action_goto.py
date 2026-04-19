"""Tests for motion.goto action behavior."""

from roamer.platform.contract import ErrorCode
from roamer.plugins.motion.actions.goto import MotionGotoAction


class _GuardFailDriver:
    def has_capability(self, name):
        return {"ok": True, "available": False}


class _NonWaitDriver:
    def has_capability(self, name):
        return {"ok": True, "available": True}

    def get_status(self):
        return {"ok": True, "status": "idle"}

    def get_position(self):
        return {"ok": True, "x": 10, "y": 20, "angle": 90}

    def goto(self, x, y):
        return {"ok": True, "response": {"accepted": True}}


class _WaitSuccessDriver(_NonWaitDriver):
    def __init__(self):
        self._status_calls = 0

    def get_status(self):
        self._status_calls += 1
        if self._status_calls == 1:
            return {"ok": True, "status": "moving"}
        return {"ok": True, "status": "idle"}

    def get_position(self):
        return {"ok": True, "x": 100, "y": 100, "angle": 0}

    def distance_to_target(self, position, tx, ty):
        return 5.0


class _WaitTimeoutDriver(_NonWaitDriver):
    def get_status(self):
        return {"ok": True, "status": "moving"}

    def get_position(self):
        return {"ok": True, "x": 0, "y": 0, "angle": 0}

    def distance_to_target(self, position, tx, ty):
        return 999.0


class _WaitErrorDriver(_NonWaitDriver):
    def get_status(self):
        return {"ok": True, "status": "error"}


def _motion_cfg(wait_timeout: float) -> dict:
    return {
        "motion": {
            "wait_timeout_sec": wait_timeout,
            "poll_interval_sec": 0.01,
            "arrival_tolerance": 20,
        }
    }


def test_goto_guard_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.goto.ValetudoMotionDriver",
        lambda cfg: _GuardFailDriver(),
    )

    action = MotionGotoAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(x=1, y=2, wait=False)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.MOTION_GOTO_GUARD_FAILED


def test_goto_without_wait_accepts(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.goto.ValetudoMotionDriver",
        lambda cfg: _NonWaitDriver(),
    )

    action = MotionGotoAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(x=100, y=100, wait=False)

    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["waiting"] is False


def test_goto_wait_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.goto.ValetudoMotionDriver",
        lambda cfg: _WaitSuccessDriver(),
    )

    action = MotionGotoAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(x=100, y=100, wait=True)

    assert result["ok"] is True
    assert result["waiting"] is True
    assert result["status"] == "idle"


def test_goto_wait_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.goto.ValetudoMotionDriver",
        lambda cfg: _WaitTimeoutDriver(),
    )

    action = MotionGotoAction(config=_motion_cfg(wait_timeout=0.02))
    result = action.run(x=100, y=100, wait=True)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.MOTION_GOTO_TIMEOUT


def test_goto_wait_robot_error_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.goto.ValetudoMotionDriver",
        lambda cfg: _WaitErrorDriver(),
    )

    action = MotionGotoAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(x=100, y=100, wait=True)

    assert result["ok"] is False
    assert result["error_code"] == ErrorCode.MOTION_GOTO_GUARD_FAILED
