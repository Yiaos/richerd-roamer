"""Minimal roamerd CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from roamer.platform.contract import SCHEMA_VERSION, exit_category_for_error
from roamerd.app import build_runtime
from roamerd.bridges.control.bridge import ControlBridge
from roamerd.config.loader import load_config
from roamerd.events.base import JSONDict
from roamerd.events.control import ControlCommandPayload, WaitMode


async def _amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roamerd")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--mock-drivers", action="store_true")
    parser.add_argument("--socket", type=str, default=None)
    parser.add_argument("command", nargs="?", default="status")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    socket_path = (
        args.socket
        if args.socket is not None
        else config.bridges.control.socket
        if args.command == "serve"
        else None
    )
    runtime = build_runtime(config, mock_drivers=args.mock_drivers, control_socket_path=socket_path)
    await runtime.start()
    await runtime.bus.drain_once()
    try:
        if args.command == "serve":
            await asyncio.Event().wait()
            return 0
        return await _run_finite_command(runtime.control, args.command, args.args)
    finally:
        await runtime.stop()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


async def _run_finite_command(control: ControlBridge, command: str, args: list[str]) -> int:
    if command == "status":
        response = await control.query("runtime.status")
        return _emit_legacy(command, response)
    if command == "ping":
        response = await control.query("ping")
        return _emit_legacy(command, response)
    if command == "health":
        response = await control.query("health")
        return _emit_legacy(command, response)
    if command == "sense":
        parsed = _parse_sense_args(args)
        response = await control.request(
            ControlCommandPayload(
                op="query",
                target="body.status",
                args={"full": bool(parsed.full)},
                correlation_id=uuid4().hex[:12],
            )
        )
        return _emit_legacy(command, response)
    if command == "watch":
        payload = _parse_watch_args(args)
        response = await _run_action(control, "watch", payload)
        return _emit_legacy(command, response)
    if command == "listen":
        parsed = _parse_listen_args(args)
        response = await _run_action(control, "listen", parsed.payload)
        if parsed.text_only and bool(response.get("ok", False)):
            result = response.get("result")
            print(str(result.get("text", "")) if isinstance(result, dict) else "")
            return 0
        return _emit_legacy(command, response)
    if command == "speak":
        response = await _run_action(control, "speak", _parse_speak_args(args))
        return _emit_legacy(command, response)
    if command == "motion":
        action, payload = _parse_motion_args(args)
        response = await _run_action(control, action, payload)
        return _emit_legacy(action, response)
    return _emit_legacy(
        command,
        {
            "ok": False,
            "error_code": "action.not_found",
            "error_message": f"Unknown command: {command}",
        },
    )


async def _run_action(control: ControlBridge, action: str, args: JSONDict) -> JSONDict:
    return await control.request(
        ControlCommandPayload(
            op="run",
            action=action,
            args=args,
            wait=WaitMode.COMPLETED,
            correlation_id=uuid4().hex[:12],
        )
    )


def _parse_sense_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="roamerd sense")
    parser.add_argument("--full", action="store_true")
    return parser.parse_args(args)


def _parse_watch_args(args: list[str]) -> JSONDict:
    parser = argparse.ArgumentParser(prog="roamerd watch")
    parser.add_argument("--output", "-o", type=str, default=None)
    parser.add_argument("--width", "-w", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parsed = parser.parse_args(args)
    payload: JSONDict = {}
    if parsed.output is not None:
        payload["output"] = parsed.output
    if parsed.width is not None:
        payload["width"] = parsed.width
    if parsed.height is not None:
        payload["height"] = parsed.height
    return payload


class _ListenArgs(argparse.Namespace):
    payload: JSONDict
    text_only: bool


def _parse_listen_args(args: list[str]) -> _ListenArgs:
    parser = argparse.ArgumentParser(prog="roamerd listen")
    parser.add_argument("--timeout", "-t", type=float, default=10.0)
    parser.add_argument("--save-audio", type=str, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--text-only", action="store_true")
    parsed = parser.parse_args(args)
    payload: JSONDict = {"timeout": parsed.timeout, "debug": parsed.debug}
    if parsed.save_audio is not None:
        payload["audio_path"] = parsed.save_audio
    result = _ListenArgs()
    result.payload = payload
    result.text_only = bool(parsed.text_only)
    return result


def _parse_speak_args(args: list[str]) -> JSONDict:
    parser = argparse.ArgumentParser(prog="roamerd speak")
    parser.add_argument("text", nargs="?")
    parser.add_argument("--stdin", dest="from_stdin", action="store_true")
    parser.add_argument("--prefix", type=str, default="")
    parser.add_argument("--save", type=str, default=None)
    parser.add_argument("--style", "-s", type=str, default=None)
    parser.add_argument("--no-play", action="store_true")
    parsed = parser.parse_args(args)
    if parsed.from_stdin:
        if parsed.text is not None:
            parser.error("Cannot provide TEXT argument when using --stdin")
        text = sys.stdin.read().strip()
    else:
        text = str(parsed.text or "")
    payload: JSONDict = {"text": f"{parsed.prefix}{text}", "play": not parsed.no_play}
    if parsed.save is not None:
        payload["save_path"] = parsed.save
    if parsed.style is not None:
        payload["style"] = parsed.style
    return payload


def _parse_motion_args(args: list[str]) -> tuple[str, JSONDict]:
    if not args:
        return "motion.status", {}
    subcommand = args[0]
    rest = args[1:]
    if subcommand in {"status", "position", "home"}:
        parser = argparse.ArgumentParser(prog=f"roamerd motion {subcommand}")
        if subcommand == "home":
            parser.add_argument("--wait", action="store_true")
        parsed = parser.parse_args(rest)
        payload: JSONDict = {}
        if subcommand == "home":
            payload["wait"] = bool(parsed.wait)
        return f"motion.{subcommand}", payload
    if subcommand == "goto":
        parser = argparse.ArgumentParser(prog="roamerd motion goto")
        parser.add_argument("--point", type=str, default=None)
        parser.add_argument("--x", type=float, default=None)
        parser.add_argument("--y", type=float, default=None)
        parser.add_argument("--angle", type=float, default=None)
        parser.add_argument("--wait", action="store_true")
        parsed = parser.parse_args(rest)
        if parsed.point is not None:
            if parsed.x is not None or parsed.y is not None:
                parser.error("Cannot combine --point with --x/--y")
            point_payload: JSONDict = {"location": parsed.point, "wait": bool(parsed.wait)}
            if parsed.angle is not None:
                point_payload["angle"] = parsed.angle
            return "motion.goto", point_payload
        if parsed.x is None or parsed.y is None:
            parser.error("Must provide --point or both --x and --y")
        target: JSONDict = {"x": parsed.x, "y": parsed.y}
        if parsed.angle is not None:
            target["angle"] = parsed.angle
        return "motion.goto", {"target": target, "wait": bool(parsed.wait)}
    return "motion." + subcommand, {}


def _print_json(payload: JSONDict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _emit_legacy(command: str, response: JSONDict) -> int:
    payload = _legacy_payload(command, response)
    _print_json(payload)
    return _exit_code(payload)


def _legacy_payload(command: str, response: JSONDict) -> JSONDict:
    ok = bool(response.get("ok", False))
    if not ok:
        return _legacy_error_payload(command, response)

    result = response.get("result")
    payload: JSONDict = {"ok": True}
    if isinstance(result, dict):
        payload.update(result)
        payload["result"] = result
    elif result is not None:
        payload["result"] = result
    for key in ("action_id", "correlation_id", "request_id"):
        if key in response:
            payload[key] = response[key]
    payload["schema_version"] = SCHEMA_VERSION
    payload["command"] = command
    return payload


def _legacy_error_payload(command: str, response: JSONDict) -> JSONDict:
    result = response.get("result")
    nested = result if isinstance(result, dict) else {}
    error_code = str(nested.get("error_code") or response.get("error_code") or "unknown_error")
    message = str(
        nested.get("error_message")
        or response.get("error_message")
        or response.get("message")
        or "Unknown runtime error"
    )
    payload: JSONDict = {
        "ok": False,
        "error": "runtime_error",
        "message": message,
        "error_code": error_code,
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "exit_category": int(exit_category_for_error(error_code)),
    }
    for key in ("action_id", "correlation_id", "request_id"):
        if key in response:
            payload[key] = response[key]
    return payload


def _exit_code(payload: JSONDict) -> int:
    if bool(payload.get("ok", False)):
        return 0
    exit_category = payload.get("exit_category")
    return int(exit_category) if isinstance(exit_category, int) else 1
