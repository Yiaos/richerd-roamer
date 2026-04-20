"""Safety guards for motion unit tests.

These tests must never issue real HTTP requests to a live robot.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_real_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast if a motion unit test accidentally uses real urlopen.

    Motion driver unit tests should always inject a fake ``urlopen``.
    """

    def _deny_real_urlopen(*_args, **_kwargs):
        raise AssertionError(
            "Unexpected real HTTP call in motion unit test. "
            "Inject a fake urlopen instead of touching live hardware."
        )

    monkeypatch.setattr(
        "roamer.plugins.motion.drivers.valetudo.urllib_request.urlopen",
        _deny_real_urlopen,
    )
