"""Config-driven driver registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from roamerd.contracts.exceptions import DriverNotFoundError

T = TypeVar("T")


class DriverRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], T]] = {}

    def register(self, name: str, factory: Callable[[], T]) -> None:
        self._factories[name] = factory

    def create(self, name: str) -> T:
        factory = self._factories.get(name)
        if factory is None:
            raise DriverNotFoundError(name)
        return factory()

    def names(self) -> list[str]:
        return sorted(self._factories)
