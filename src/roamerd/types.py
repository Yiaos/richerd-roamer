from __future__ import annotations

from typing import TypeAlias

from pydantic import JsonValue

JSONValue: TypeAlias = JsonValue
JSONDict: TypeAlias = dict[str, JSONValue]
