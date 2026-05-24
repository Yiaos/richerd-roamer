import pytest

from roamerd.config.schema import RoamerdConfig
from roamerd.kernel import EventBus, StateManager


@pytest.fixture
def mock_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mock_config() -> RoamerdConfig:
    return RoamerdConfig()


@pytest.fixture
def mock_state_manager() -> StateManager:
    return StateManager(session_id="session-1")
