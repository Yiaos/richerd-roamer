from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import yaml

from roamerd.config.schema import RoamerdConfig
from roamerd.types import JSONValue


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "roamerd.yaml"


def load_config(path: Path | None = None) -> RoamerdConfig:
    config_data = _model_dict(RoamerdConfig())
    config_path = path or default_config_path()
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        _deep_merge(config_data, cast(dict[str, JSONValue], _expand_env(loaded)))
    return RoamerdConfig.model_validate(config_data)


def _model_dict(config: RoamerdConfig) -> dict[str, JSONValue]:
    return cast(dict[str, JSONValue], config.model_dump(mode="json"))


def _expand_env(value: object) -> object:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _expand_env(item) for key, item in value.items()}
    return value


def _deep_merge(base: dict[str, JSONValue], override: dict[str, JSONValue]) -> None:
    for key, value in override.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _deep_merge(current, value)
        else:
            base[key] = value
