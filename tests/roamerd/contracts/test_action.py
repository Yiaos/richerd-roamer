from roamerd.contracts.action import ActionRequest, ActionStatus, PreemptionScope
from roamerd.events import Priority


def test_action_contract_types_are_stable() -> None:
    request = ActionRequest(
        action_type="speech.speak",
        payload={"text": "hello"},
        resource="speaker",
        priority=Priority.HIGH,
        source="test",
    )
    scope = PreemptionScope(
        target_resources=["motion"],
        reason="safety",
        source_event="event-1",
    )

    assert request.action_type == "speech.speak"
    assert request.payload == {"text": "hello"}
    assert ActionStatus.RUNNING_DETACHED == "running_detached"
    assert scope.target_resources == ["motion"]
