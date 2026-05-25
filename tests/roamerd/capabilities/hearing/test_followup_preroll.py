import pytest

from roamerd.capabilities.hearing.followup import FollowupCoordinator
from roamerd.capabilities.hearing.preroll import PreRollAudioSource


def test_followup_coordinator_ignores_stale_generation() -> None:
    coordinator = FollowupCoordinator()
    old = coordinator.open_window()
    new = coordinator.open_window()

    assert coordinator.close_if_current(old) is False
    assert coordinator.open is True
    assert coordinator.close_if_current(new) is True
    assert coordinator.open is False


@pytest.mark.asyncio
async def test_preroll_audio_source_records_playback() -> None:
    source = PreRollAudioSource()

    await source.play()

    assert source.played is True
