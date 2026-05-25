from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from types import FrameType

from roamerd import __version__

_termination_requested = False
_shutdown_loop: asyncio.AbstractEventLoop | None = None
_shutdown_event: asyncio.Event | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m roamerd")
    parser.add_argument("--config", default="config/roamerd.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--version", action="version", version=f"roamerd {__version__}")
    parser.add_argument("legacy_args", nargs=argparse.REMAINDER)
    return parser


def _request_shutdown(_: int, __: FrameType | None) -> None:
    global _termination_requested
    _termination_requested = True
    if _shutdown_loop is not None and _shutdown_event is not None:
        _shutdown_loop.call_soon_threadsafe(_shutdown_event.set)


async def _run(args: argparse.Namespace) -> int:
    global _shutdown_event, _shutdown_loop
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    _shutdown_loop = loop
    _shutdown_event = stop_event
    if _termination_requested:
        stop_event.set()

    from roamerd.app import create_app
    from roamerd.config.loader import load_config

    config = load_config(Path(args.config))
    if args.dry_run:
        print("dry-run ok")
        print(f"hearing={config.capabilities.hearing.audio.driver}")
        print(f"speech={config.capabilities.speech.playback.driver}")
        print(f"vision={config.capabilities.vision.camera.driver}")
        print(f"motion={config.capabilities.motion.driver}")
        return 0
    app = create_app(config)
    await app.start()
    bus_runner = asyncio.create_task(app.event_bus.run())
    print("roamerd started", flush=True)
    try:
        await stop_event.wait()
    finally:
        await app.stop()
        await bus_runner
        _shutdown_event = None
        _shutdown_loop = None
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.legacy_args:
        from roamerd.compat.legacy_cli import main as legacy_main

        return legacy_main(["--config", str(args.config), *args.legacy_args])
    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)
    try:
        return asyncio.run(_run(args))
    except Exception as exc:
        print(f"roamerd: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
