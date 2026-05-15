"""Local interpreter startup adjustments for the repository test environment."""

from __future__ import annotations

import sys
import types

if sys.modules.get("readline") is None:
    readline = types.ModuleType("readline")

    def _noop(*_: object, **__: object) -> None:
        return None

    readline.parse_and_bind = _noop  # type: ignore[attr-defined]
    readline.set_completer = _noop  # type: ignore[attr-defined]
    readline.get_completer = lambda: None  # type: ignore[attr-defined]
    readline.read_history_file = _noop  # type: ignore[attr-defined]
    readline.write_history_file = _noop  # type: ignore[attr-defined]
    readline.set_history_length = _noop  # type: ignore[attr-defined]
    sys.modules["readline"] = readline
