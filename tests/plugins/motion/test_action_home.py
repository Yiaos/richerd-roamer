"""Tests for motion.home action behavior."""

from roamer.plugins.motion.actions.home import MotionHomeAction


class _DriverImmediate:
    def home(self):
        return {"ok": True, "response": {"accepted": True}}


class _DriverWaitSuccess:
    def __init__(self):
        self.calls = 0

    def home(self):
        return {"ok": True, "response": {"accepted": True}}

    def get_status(self):
        self.calls += 1
        if self.calls == 1:
            return {"ok": True, "status": "returning", "battery_percent": 50}
        return {"ok": True, "status": "docked", "battery_percent": 49}


class _DriverWaitTimeout:
    def home(self):
        return {"ok": True, "response": {"accepted": True}}

    def get_status(self):
        return {"ok": True, "status": "returning", "battery_percent": 50}


class _DriverErrorState:
    def home(self):
        return {"ok": True, "response": {"accepted": True}}

    def get_status(self):
        return {"ok": True, "status": "error"}


def _motion_cfg(wait_timeout: float) -> dict:
    return {
        "motion": {
            "wait_timeout_sec": wait_timeout,
            "poll_interval_sec": 0.01,
        }
    }


def test_home_without_wait_returns_accepted(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.home.ValetudoMotionDriver",
        lambda cfg: _DriverImmediate(),
    )

    action = MotionHomeAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(wait=False)

    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["waiting"] is False


def test_home_wait_succeeds_when_docked(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.home.ValetudoMotionDriver",
        lambda cfg: _DriverWaitSuccess(),
    )

    action = MotionHomeAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(wait=True)

    assert result["ok"] is True
    assert result["waiting"] is True
    assert result["status"] == "docked"


def test_home_wait_times_out(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.home.ValetudoMotionDriver",
        lambda cfg: _DriverWaitTimeout(),
    )

    action = MotionHomeAction(config=_motion_cfg(wait_timeout=0.02))
    result = action.run(wait=True)

    assert result["ok"] is False
    assert result["error_code"] == "motion.home.timeout"


def test_home_wait_error_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "roamer.plugins.motion.actions.home.ValetudoMotionDriver",
        lambda cfg: _DriverErrorState(),
    )

    action = MotionHomeAction(config=_motion_cfg(wait_timeout=1))
    result = action.run(wait=True)

    assert result["ok"] is False
    assert result["error_code"] == "motion.home.failed"
