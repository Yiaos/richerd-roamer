"""roamerd config package."""

from pathlib import Path

from roamerd.config.schema import RoamerdConfig

__all__ = ["RoamerdConfig", "load_config"]


def load_config(path: Path | None = None) -> RoamerdConfig:
    from roamerd.config.loader import load_config as _load_config

    return _load_config(path)
