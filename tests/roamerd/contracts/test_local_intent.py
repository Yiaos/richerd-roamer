from roamerd.contracts.local_intent import ALLOWED_INTENT_ACTIONS, IntentConfig, LocalIntentMatch
from roamerd.events import Priority


def test_local_intent_contract_exposes_allowlist_and_match_shape() -> None:
    config = IntentConfig(
        name="go_home",
        action="motion.home",
        patterns=["回充电"],
        priority=Priority.HIGH,
    )
    match = LocalIntentMatch(
        matched=True,
        intent_name="go_home",
        action_type="motion.home",
        slots={},
        priority=Priority.HIGH,
    )

    assert "motion.home" in ALLOWED_INTENT_ACTIONS
    assert config.action == match.action_type
