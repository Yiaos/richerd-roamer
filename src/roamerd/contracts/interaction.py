"""Interaction contract namespace."""

from roamerd.events.hearing import TranscriptPayload, WakePayload
from roamerd.events.speech import PlaybackPayload, SpeakRequestPayload

__all__ = ["PlaybackPayload", "SpeakRequestPayload", "TranscriptPayload", "WakePayload"]
