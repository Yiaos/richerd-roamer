"""Roamer CLI - Command line interface."""

import json
from pathlib import Path

import click

from roamer.config import load_config


def output_json(data: dict) -> None:
    """Output data as JSON to stdout."""
    click.echo(json.dumps(data, ensure_ascii=False))


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
    ctx.obj["config"] = load_config(config)


# Camera commands
@main.group()
def camera() -> None:
    """Camera commands."""
    pass


@camera.command("snap")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--width", "-w", type=click.IntRange(1, 7680), default=1280, help="Image width")
@click.option("--height", type=click.IntRange(1, 4320), default=720, help="Image height")
@click.pass_context
def camera_snap(ctx: click.Context, output: str | None, width: int, height: int) -> None:
    """Capture an image."""
    from roamer.capabilities.camera import CameraCapability

    cap = CameraCapability(ctx.obj["config"])
    result = cap.snap(output=output, width=width, height=height)
    output_json(result)


# Audio commands
@main.group()
def audio() -> None:
    """Audio commands."""
    pass


@audio.command("record")
@click.option("--duration", "-d", type=float, default=5.0, help="Recording duration in seconds")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.pass_context
def audio_record(ctx: click.Context, duration: float, output: str | None) -> None:
    """Record audio from microphone."""
    from roamer.capabilities.audio import AudioCapability

    cap = AudioCapability(ctx.obj["config"])
    result = cap.record(duration=duration, output=output)
    output_json(result)


@audio.command("play")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def audio_play(ctx: click.Context, file: str) -> None:
    """Play an audio file."""
    from roamer.capabilities.audio import AudioCapability

    cap = AudioCapability(ctx.obj["config"])
    result = cap.play(file)
    output_json(result)


# Bluetooth commands
@main.group()
def bt() -> None:
    """Bluetooth commands."""
    pass


@bt.command("status")
@click.pass_context
def bt_status(ctx: click.Context) -> None:
    """Show Bluetooth status."""
    from roamer.capabilities.bluetooth import BluetoothCapability

    cap = BluetoothCapability(ctx.obj["config"])
    result = cap.status()
    output_json(result)


@bt.command("connect")
@click.argument("address")
@click.pass_context
def bt_connect(ctx: click.Context, address: str) -> None:
    """Connect to a Bluetooth device."""
    from roamer.capabilities.bluetooth import BluetoothCapability

    cap = BluetoothCapability(ctx.obj["config"])
    result = cap.connect(address)
    output_json(result)


# Speech commands
@main.command()
@click.argument("text")
@click.option("--save", "-s", type=click.Path(), help="Save audio to file")
@click.option("--no-play", is_flag=True, help="Don't play audio, just synthesize")
@click.pass_context
def speak(ctx: click.Context, text: str, save: str | None, no_play: bool) -> None:
    """Text to speech."""
    from roamer.capabilities.speech import SpeechCapability

    cap = SpeechCapability(ctx.obj["config"])
    result = cap.speak(text, save_path=save, play=not no_play)
    output_json(result)


@main.command()
@click.option("--timeout", "-t", type=float, default=10.0, help="Listen timeout in seconds")
@click.option("--save-audio", type=click.Path(), help="Save recorded audio to file")
@click.pass_context
def listen(ctx: click.Context, timeout: float, save_audio: str | None) -> None:
    """Listen and transcribe speech."""
    from roamer.capabilities.speech import SpeechCapability

    cap = SpeechCapability(ctx.obj["config"])
    result = cap.listen(timeout=timeout, save_audio=save_audio)
    output_json(result)


# System commands
@main.command()
@click.option("--full", is_flag=True, help="Show full status including hardware checks")
@click.pass_context
def status(ctx: click.Context, full: bool) -> None:
    """Show system status."""
    from roamer.capabilities.system import SystemCapability

    cap = SystemCapability(ctx.obj["config"])
    result = cap.status(full=full)
    output_json(result)


if __name__ == "__main__":
    main()
