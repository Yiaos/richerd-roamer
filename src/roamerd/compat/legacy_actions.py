"""Legacy action names mapped to the new ControlBridge."""

from __future__ import annotations

from roamerd.bridges.control.bridge import ControlBridge
from roamerd.events.base import JSONDict

LEGACY_ACTION_MAP: dict[str, str] = {
    "watch": "watch",
    "sense": "sense",
    "listen": "listen",
    "speak": "speak",
    "remind": "remind.schedule",
    "motion.status": "motion.status",
    "motion.position": "motion.position",
    "motion.locate": "motion.locate",
    "motion.home": "motion.home",
    "motion.goto": "motion.goto",
}


async def run_legacy_action(
    bridge: ControlBridge, action_name: str, **kwargs: JSONDict
) -> JSONDict:
    action = LEGACY_ACTION_MAP.get(action_name)
    if action is None:
        return {
            "ok": False,
            "error_code": "action.not_found",
            "error_message": f"Unknown action: {action_name}",
        }
    return await bridge.run(action, dict(kwargs))
