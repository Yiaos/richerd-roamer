"""TTS drivers for interaction plugin."""

from roamer.plugins.interaction.drivers.speech.tts.edge import EdgeDriver
from roamer.plugins.interaction.drivers.speech.tts.piper import PiperDriver

__all__ = ["EdgeDriver", "PiperDriver"]
