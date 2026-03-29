"""Roamer capabilities - action-based perception and output."""

from roamer.capabilities.listen import ListenCapability
from roamer.capabilities.sense import SenseCapability
from roamer.capabilities.speak import SpeakCapability
from roamer.capabilities.watch import WatchCapability

__all__ = [
    "WatchCapability",
    "SpeakCapability",
    "ListenCapability",
    "SenseCapability",
]
