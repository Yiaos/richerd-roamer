from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from roamerd.bridges.control.ipc import ControlClient
from roamerd.bridges.control.protocol import RequestEnvelope
from roamerd.config.loader import load_config
from roamerd.types import JSONDict


class LegacyCliError(ValueError):
    pass


def legacy_request(argv: list[str], *, request_id: str = "legacy") -> RequestEnvelope:
    command = argv[0] if argv else ""
    if command == "serve":
        return _serve_request(argv[1:], request_id=request_id)
    if command == "motion":
        return _motion_request(argv[1:], request_id=request_id)
    if command == "audio":
        return _audio_request(argv[1:], request_id=request_id)
    if command == "bt":
        return _bt_request(argv[1:], request_id=request_id)
    if command == "ping":
        return RequestEnvelope(
            request_id=request_id,
            client="legacy_cli",
            source="cli",
            op="ping",
        )
    if command == "status":
        return RequestEnvelope(
            request_id=request_id,
            client="legacy_cli",
            source="cli",
            op="status",
        )
    if command == "sense":
        return RequestEnvelope(
            request_id=request_id,
            client="legacy_cli",
            source="cli",
            op="run",
            args={"action": "sense", "resource": "none", "payload": {}},
        )
    if command == "speak":
        text = " ".join(argv[1:])
        if not text:
            raise LegacyCliError("speak requires text")
        return RequestEnvelope(
            request_id=request_id,
            client="legacy_cli",
            source="cli",
            op="run",
            args={
                "action": "speech.speak",
                "resource": "speaker",
                "payload": {"text": text},
            },
        )
    if command == "remind":
        if len(argv) < 3 or argv[1] != "--after":
            raise LegacyCliError("remind requires --after DELAY TEXT")
        return _run_request(
            request_id,
            "remind.schedule",
            "none",
            {"delay": argv[2], "text": " ".join(argv[3:])},
        )
    if command == "listen":
        return _run_request(request_id, "hearing.listen", "microphone", {})
    if command == "watch":
        return _run_request(request_id, "watch", "camera", {})
    if command == "home":
        return _run_request(request_id, "motion.home", "motion", {})
    if command == "goto":
        return _goto_request(argv[1:], request_id=request_id)
    if command in {"converse", "wake"}:
        return RequestEnvelope(
            request_id=request_id,
            client="legacy_cli",
            source="cli",
            op="session.start",
            args={"kind": command},
        )
    if command == "init":
        return _run_request(request_id, "system.init", "none", {})
    raise LegacyCliError(f"unknown legacy command: {command or '<empty>'}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    config_path = _extract_config_path(args)
    if args[:1] == ["serve"] and len(args) == 1:
        from roamerd.__main__ import main as roamerd_main

        sys.argv = ["python -m roamerd", "--config", str(config_path or "config/roamerd.yaml")]
        return roamerd_main()
    try:
        request = legacy_request(args)
        config = load_config(config_path)
        response = asyncio.run(
            ControlClient(Path(config.bridges.control.socket)).request(request)
        )
    except LegacyCliError as exc:
        print(f"roamer: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"roamer: control bridge unavailable: {exc}", file=sys.stderr)
        return 69
    print(response.model_dump_json(exclude_none=True))
    return 0 if response.status == "ok" else 1


def _run_request(
    request_id: str,
    action: str,
    resource: str,
    payload: JSONDict,
) -> RequestEnvelope:
    return RequestEnvelope(
        request_id=request_id,
        client="legacy_cli",
        source="cli",
        op="run",
        args={"action": action, "resource": resource, "payload": payload},
    )


def _serve_request(argv: list[str], *, request_id: str) -> RequestEnvelope:
    subcommand = argv[0] if argv else ""
    if subcommand == "ping":
        return legacy_request(["ping"], request_id=request_id)
    if subcommand == "status":
        return legacy_request(["status"], request_id=request_id)
    raise LegacyCliError("serve supports ping/status, or no subcommand to run roamerd")


def _motion_request(argv: list[str], *, request_id: str) -> RequestEnvelope:
    subcommand = argv[0] if argv else ""
    if subcommand == "status":
        return _run_request(request_id, "motion.position", "motion", {})
    if subcommand == "position":
        return _run_request(request_id, "motion.position", "motion", {})
    if subcommand == "home":
        return _run_request(request_id, "motion.home", "motion", {})
    if subcommand == "goto":
        return _goto_request(argv[1:], request_id=request_id)
    raise LegacyCliError(f"unsupported motion command: {subcommand or '<empty>'}")


def _audio_request(argv: list[str], *, request_id: str) -> RequestEnvelope:
    subcommand = argv[0] if argv else ""
    if subcommand == "record":
        return _run_request(request_id, "hearing.listen", "microphone", {})
    if subcommand == "play":
        if len(argv) < 2:
            raise LegacyCliError("audio play requires file")
        return _run_request(request_id, "speech.speak", "speaker", {"audio_file": argv[1]})
    raise LegacyCliError(f"unsupported audio command: {subcommand or '<empty>'}")


def _bt_request(argv: list[str], *, request_id: str) -> RequestEnvelope:
    subcommand = argv[0] if argv else ""
    if subcommand == "status":
        return RequestEnvelope(
            request_id=request_id,
            client="legacy_cli",
            source="cli",
            op="status",
        )
    if subcommand == "connect":
        return _run_request(request_id, "speech.bluetooth.connect", "speaker", {})
    raise LegacyCliError(f"unsupported bt command: {subcommand or '<empty>'}")


def _goto_request(argv: list[str], *, request_id: str) -> RequestEnvelope:
    if len(argv) < 2:
        raise LegacyCliError("goto requires X Y [ANGLE]")
    target: JSONDict = {"x": float(argv[0]), "y": float(argv[1])}
    if len(argv) >= 3:
        target["angle"] = float(argv[2])
    return _run_request(request_id, "motion.goto", "motion", {"target": target})


def _extract_config_path(argv: list[str]) -> Path | None:
    for option in ("--config", "-c"):
        if option not in argv:
            continue
        index = argv.index(option)
        if index + 1 >= len(argv):
            raise LegacyCliError(f"{option} requires a path")
        value = Path(argv[index + 1])
        del argv[index : index + 2]
        return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
