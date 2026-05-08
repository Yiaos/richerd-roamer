"""Tests for cross-process playback state."""

import json
import time

from roamer.plugins.interaction.services.playback_state import PlaybackState


def test_playback_state_marks_active_and_finished_across_instances(tmp_path) -> None:
    first = PlaybackState(tmp_path)
    second = PlaybackState(tmp_path)

    started = first.mark_started(request_id="req1", source="speak")

    assert started["active"] is True
    assert second.is_active() is True
    assert second.snapshot()["request_id"] == "req1"

    finished = second.mark_finished(playback_id=started["playback_id"], source="speak")

    assert finished["active"] is False
    assert finished["generation"] == started["generation"] + 1
    assert first.is_active() is False
    assert first.generation() == finished["generation"]


def test_playback_state_finish_clears_active_even_without_started_file(tmp_path) -> None:
    state = PlaybackState(tmp_path)

    result = state.mark_finished(request_id="req1", source="speak")

    assert result["active"] is False
    assert state.is_active() is False
    assert state.generation() == 0


def test_playback_state_keeps_active_until_all_overlapping_playbacks_finish(tmp_path) -> None:
    state = PlaybackState(tmp_path)
    first = state.mark_started(request_id="req1", source="speak")
    second = state.mark_started(request_id="req2", source="speak")

    first_finished = state.mark_finished(playback_id=first["playback_id"], source="speak")

    assert first_finished["active"] is True
    assert first_finished["generation"] == first["generation"]
    assert state.is_active() is True

    second_finished = state.mark_finished(playback_id=second["playback_id"], source="speak")

    assert second_finished["active"] is False
    assert second_finished["generation"] == first["generation"] + 1
    assert state.is_active() is False


def test_playback_state_clears_stale_marker(tmp_path) -> None:
    state = PlaybackState(tmp_path, stale_after_sec=1.0)
    started = state.mark_started(request_id="req1", source="speak")
    marker_path = state.marker_dir / f"{started['playback_id']}.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["started_at_epoch"] = time.time() - 5
    marker["expires_at_epoch"] = time.time() - 4
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    assert state.is_active() is False
    assert marker_path.exists() is False
    assert state.generation() == started["generation"] + 1
