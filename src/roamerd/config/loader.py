"""Configuration loading for roamerd."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from roamerd.compat.legacy_config import load_config as load_legacy_config
from roamerd.config.schema import RoamerdConfig, default_roamerd_config_path


def load_config(path: Path | None = None) -> RoamerdConfig:
    resolved = path or default_roamerd_config_path()
    if resolved.exists():
        with open(resolved) as handle:
            loaded = yaml.safe_load(handle) or {}
        return RoamerdConfig.model_validate(loaded)
    return load_legacy_config(None)
