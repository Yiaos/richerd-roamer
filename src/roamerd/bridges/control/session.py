from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass
class Session:
    session_id: str
    kind: str
    active: bool = True


class SessionCoordinator:
    def __init__(self) -> None:
        self.current: Session | None = None

    def start(self, kind: str) -> Session:
        self.current = Session(session_id=uuid4().hex[:12], kind=kind)
        return self.current

    def finish(self) -> None:
        if self.current is not None:
            self.current.active = False
