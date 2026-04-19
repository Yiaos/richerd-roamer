"""Roamer CLI - Command line interface."""

import json
from pathlib import Path

import click

from roamer.platform.config import load_config
from roamer.platform.contract import exit_category_for_error
from roamer.platform.output import attach_contract_fields
from roamer.platform.plugin_registry import registry
from roamer.platform.runtime import run_action
from roamer.plugins.interaction.plugin import register as register_interaction_plugin
from roamer.plugins.motion.plugin import register as register_motion_plugin
from roamer.plugins.perception.plugin import register as register_perception_plugin


def output_json(data: dict) -> None:
    """Output data as JSON to stdout."""
    click.echo(json.dumps(data, ensure_ascii=False))


def emit_contract_result(
    ctx: click.Context,
    command: str,
    result: dict,
    *,
    text_only: bool = False,
) -> None:
    """Emit command result with deterministic contract and exit behavior."""
    payload = attach_contract_fields(result, command)
    ok = bool(payload.get("ok"))

    if text_only and ok:
        click.echo(payload.get("text", ""))
        ctx.exit(0)

    if not ok:
        failure_exit = exit_category_for_error(payload.get("error_code")).value
        if text_only:
            click.echo(json.dumps(payload, ensure_ascii=False), err=True)
            ctx.exit(failure_exit)
    else:
        failure_exit = 0

    output_json(payload)
    ctx.exit(0 if ok else failure_exit)


def _ensure_perception_plugin_registered(config: dict) -> None:
    """Register perception actions for current command execution."""
    for action_name in ("watch", "sense"):
        registry.remove(action_name)
    register_perception_plugin(registry, config)


def _ensure_interaction_plugin_registered(config: dict) -> None:
    """Register interaction actions for current command execution."""
    for action_name in (
        "listen",
        "speak",
        "converse",
        "audio.record",
        "audio.play",
        "bt.status",
        "bt.connect",
        "init",
    ):
        registry.remove(action_name)
    register_interaction_plugin(registry, config)


def _ensure_motion_plugin_registered(config: dict) -> None:
    """Register motion actions for current command execution."""
    for action_name in (
        "motion.status",
        "motion.position",
        "motion.locate",
        "motion.home",
        "motion.goto",
    ):
        registry.remove(action_name)
    register_motion_plugin(registry, config)


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Config file path",
)
@click.pass_context
def main(ctx: click.Context, config: Path | None) -> None:
    """Roamer - Richerd's physical body CLI."""
    ctx.ensure_object(dict)
    # Use default config path if not specified
    if config is None:
        default_config = Path.home() / ".config" / "roamer" / "config.yaml"
        if default_config.exists():
            config = default_config
    ctx.obj["config"] = load_config(config)


# Watch - visual perception
@main.command()
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--width", "-w", type=click.IntRange(1, 7680), default=1280, help="Image width")
@click.option("--height", type=click.IntRange(1, 4320), default=720, help="Image height")
@click.pass_context
def watch(ctx: click.Context, output: str | None, width: int, height: int) -> None:
    """Capture an image (visual perception)."""
    _ensure_perception_plugin_registered(ctx.obj["config"])
    result = run_action("watch", output=output, width=width, height=height)
    emit_contract_result(ctx, "watch", result)


# Speak - voice output
@main.command()
@click.argument("text", required=False)
@click.option("--stdin", "from_stdin", is_flag=True, help="Read text from stdin")
@click.option("--prefix", type=str, default="", help="Prefix to prepend to the text")
@click.option("--save", type=click.Path(), help="Save audio to file")
@click.option(
    "--style",
    "-s",
    type=str,
    default=None,
    help=(
        "Emotional style "
        "(cheerful/sad/angry/fearful/disgruntled/serious/depressed/embarrassed/gentle/lyrical)"
    ),
)
@click.option("--no-play", is_flag=True, help="Don't play audio, just synthesize")
@click.pass_context
def speak(
    ctx: click.Context,
    text: str | None,
    from_stdin: bool,
    prefix: str,
    save: str | None,
    style: str | None,
    no_play: bool,
) -> None:
    """Text to speech (voice output)."""
    if from_stdin and text is not None:
        raise click.UsageError("Cannot provide TEXT argument when using --stdin")

    input_text = click.get_text_stream("stdin").read().strip() if from_stdin else (text or "")
    speak_text = f"{prefix}{input_text}"

    if not speak_text:
        raise click.UsageError("No text provided. Use TEXT argument or --stdin.")

    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action(
        "speak",
        text=speak_text,
        save_path=save,
        play=not no_play,
        style=style,
    )
    emit_contract_result(ctx, "speak", result)


# Listen - voice input
@main.command()
@click.option("--timeout", "-t", type=float, default=10.0, help="Listen timeout in seconds")
@click.option("--save-audio", type=click.Path(), help="Save recorded audio to file")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--text-only", is_flag=True, help="Output transcribed text only")
@click.pass_context
def listen(
    ctx: click.Context,
    timeout: float,
    save_audio: str | None,
    debug: bool,
    text_only: bool,
) -> None:
    """Listen and transcribe speech (voice input)."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action(
        "listen",
        timeout=timeout,
        save_audio=save_audio,
        debug=debug,
    )
    emit_contract_result(ctx, "listen", result, text_only=text_only)


# Converse - voice wake + dialog loop
@main.command()
@click.option("--no-wakeword", is_flag=True, help="Disable wakeword and start listening immediately")
@click.option("--timeout", "silence_timeout", type=float, default=None, help="Silence timeout in seconds")
@click.option("--no-sound", is_flag=True, help="Disable prompt/ding sound")
@click.option("--max-turns", type=click.IntRange(1), default=None, help="Maximum turns before exiting")
@click.pass_context
def converse(
    ctx: click.Context,
    no_wakeword: bool,
    silence_timeout: float | None,
    no_sound: bool,
    max_turns: int | None,
) -> None:
    """Run converse loop (wakeword + continuous conversation)."""
    config = ctx.obj["config"]
    converse_config = config.get("converse", {})
    wakeword_enabled = bool(converse_config.get("wakeword", {}).get("enabled", True))

    effective_no_wakeword = no_wakeword or not wakeword_enabled
    effective_timeout = (
        float(silence_timeout)
        if silence_timeout is not None
        else float(converse_config.get("silence_timeout", 8.0))
    )
    effective_no_sound = bool(no_sound or converse_config.get("no_sound_default", False))
    effective_max_turns = (
        int(max_turns)
        if max_turns is not None
        else int(converse_config.get("max_turns", 10))
    )

    _ensure_interaction_plugin_registered(config)
    result = run_action(
        "converse",
        no_wakeword=effective_no_wakeword,
        timeout=effective_timeout,
        no_sound=effective_no_sound,
        max_turns=effective_max_turns,
    )
    emit_contract_result(ctx, "converse", result)


# Sense - self-state perception
@main.command()
@click.option("--full", is_flag=True, help="Show full status including hardware checks")
@click.pass_context
def sense(ctx: click.Context, full: bool) -> None:
    """Sense self-state (system status)."""
    _ensure_perception_plugin_registered(ctx.obj["config"])
    result = run_action("sense", full=full)
    emit_contract_result(ctx, "sense", result)


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Run Roamer-owned startup initialization."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action("init")
    emit_contract_result(ctx, "init", result)


# === Utility commands (not core capabilities) ===

# Audio - low-level audio control
@main.group()
def audio() -> None:
    """Audio utilities (low-level)."""
    pass


@audio.command("record")
@click.option("--duration", "-d", type=float, default=5.0, help="Recording duration in seconds")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.pass_context
def audio_record(ctx: click.Context, duration: float, output: str | None) -> None:
    """Record audio from microphone."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action("audio.record", duration=duration, output=output)
    emit_contract_result(ctx, "audio.record", result)


@audio.command("play")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def audio_play(ctx: click.Context, file: str) -> None:
    """Play an audio file."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action("audio.play", file=file)
    emit_contract_result(ctx, "audio.play", result)


# Bluetooth - device connection utility
@main.group()
def bt() -> None:
    """Bluetooth utilities."""
    pass


@bt.command("status")
@click.pass_context
def bt_status(ctx: click.Context) -> None:
    """Show Bluetooth status."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action("bt.status")
    emit_contract_result(ctx, "bt.status", result)


@bt.command("connect")
@click.argument("address")
@click.pass_context
def bt_connect(ctx: click.Context, address: str) -> None:
    """Connect to a Bluetooth device."""
    _ensure_interaction_plugin_registered(ctx.obj["config"])
    result = run_action("bt.connect", address=address)
    emit_contract_result(ctx, "bt.connect", result)


# Motion - base mobility capability
@main.group()
def motion() -> None:
    """Motion utilities backed by Valetudo."""
    pass


@motion.command("status")
@click.pass_context
def motion_status(ctx: click.Context) -> None:
    """Show current motion status."""
    _ensure_motion_plugin_registered(ctx.obj["config"])
    result = run_action("motion.status")
    emit_contract_result(ctx, "motion.status", result)


@motion.command("position")
@click.pass_context
def motion_position(ctx: click.Context) -> None:
    """Show current robot position."""
    _ensure_motion_plugin_registered(ctx.obj["config"])
    result = run_action("motion.position")
    emit_contract_result(ctx, "motion.position", result)


@motion.command("locate")
@click.pass_context
def motion_locate(ctx: click.Context) -> None:
    """Trigger locate action for the robot."""
    _ensure_motion_plugin_registered(ctx.obj["config"])
    result = run_action("motion.locate")
    emit_contract_result(ctx, "motion.locate", result)


@motion.command("home")
@click.option("--wait", "wait_for_done", is_flag=True, help="Wait until docked or timeout")
@click.pass_context
def motion_home(ctx: click.Context, wait_for_done: bool) -> None:
    """Send robot back to dock."""
    _ensure_motion_plugin_registered(ctx.obj["config"])
    result = run_action("motion.home", wait=wait_for_done)
    emit_contract_result(ctx, "motion.home", result)


@motion.command("goto")
@click.option("--x", type=int, required=True, help="Target X coordinate")
@click.option("--y", type=int, required=True, help="Target Y coordinate")
@click.option("--wait", "wait_for_done", is_flag=True, help="Wait until arrived or timeout")
@click.pass_context
def motion_goto(ctx: click.Context, x: int, y: int, wait_for_done: bool) -> None:
    """Navigate robot to target coordinates."""
    _ensure_motion_plugin_registered(ctx.obj["config"])
    result = run_action("motion.goto", x=x, y=y, wait=wait_for_done)
    emit_contract_result(ctx, "motion.goto", result)


if __name__ == "__main__":
    main()
