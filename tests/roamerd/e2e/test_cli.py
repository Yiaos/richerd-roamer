import asyncio
import io
import json
import sys

from roamerd.cli import _amain


def test_cli_sense_returns_body_status(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(_amain(["--mock-drivers", "sense"]), timeout=1.0)

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["schema_version"] == "1.0"
    assert output["command"] == "sense"
    assert "hostname" in output["result"]
    assert "hostname" in output


def test_cli_sense_full_passes_full_query_flag(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(_amain(["--mock-drivers", "sense", "--full"]), timeout=1.0)

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert "memory" in output["result"]
    assert "memory" in output


def test_cli_watch_returns_captured_image(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(_amain(["--mock-drivers", "watch"]), timeout=1.0)

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["schema_version"] == "1.0"
    assert output["command"] == "watch"
    assert output["result"]["path"].endswith("roamerd-image.jpg")
    assert output["path"].endswith("roamerd-image.jpg")


def test_cli_speak_runs_legacy_style_command(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(
            _amain(["--mock-drivers", "speak", "hello", "--no-play"]),
            timeout=1.0,
        )

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["schema_version"] == "1.0"
    assert output["command"] == "speak"
    assert output["result"]["text"] == "hello"
    assert output["result"]["played"] is False
    assert output["text"] == "hello"


def test_cli_speak_reads_stdin_with_prefix(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("world\n"))

    async def scenario() -> int:
        return await asyncio.wait_for(
            _amain(["--mock-drivers", "speak", "--stdin", "--prefix", "hello ", "--no-play"]),
            timeout=1.0,
        )

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["text"] == "hello world"


def test_cli_listen_text_only_returns_transcript(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(
            _amain(["--mock-drivers", "listen", "--timeout", "1", "--text-only"]),
            timeout=1.0,
        )

    assert asyncio.run(scenario()) == 0
    assert capsys.readouterr().out.strip() == "mock transcript"


def test_cli_motion_status_runs_legacy_style_command(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(
            _amain(["--mock-drivers", "motion", "status"]),
            timeout=1.0,
        )

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["schema_version"] == "1.0"
    assert output["command"] == "motion.status"
    assert output["result"]["battery_percent"] == 100
    assert output["battery_percent"] == 100


def test_cli_motion_locate_runs_legacy_style_command(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(
            _amain(["--mock-drivers", "motion", "locate"]),
            timeout=1.0,
        )

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["schema_version"] == "1.0"
    assert output["command"] == "motion.locate"
    assert output["result"]["action"] == "locate"


def test_cli_motion_goto_point_resolves_legacy_named_point(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(
            _amain(
                [
                    "--mock-drivers",
                    "motion",
                    "goto",
                    "--point",
                    "阳台",
                    "--angle",
                    "90",
                    "--wait",
                ]
            ),
            timeout=1.0,
        )

    assert asyncio.run(scenario()) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["command"] == "motion.goto"
    assert output["final_position"] == {
        "x": 2082.0,
        "y": 2377.0,
        "angle": 90.0,
        "frame": "valetudo_pixel",
    }


def test_cli_unknown_command_returns_error_without_hanging(capsys) -> None:
    async def scenario() -> int:
        return await asyncio.wait_for(_amain(["--mock-drivers", "unknown"]), timeout=1.0)

    assert asyncio.run(scenario()) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["error_code"] == "action.not_found"
    assert output["schema_version"] == "1.0"
    assert output["command"] == "unknown"
    assert output["exit_category"] == 2
