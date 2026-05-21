# -*- coding: utf-8 -*-

import subprocess
from pathlib import Path
from typing import NamedTuple

from .main import AudioDeviceOptions


class AudioCommandResult(NamedTuple):
    command: list[str]
    return_code: int
    stdout: str
    stderr: str


_FORMAT_ALIASES = {
    's8': 'S8',
    'u8': 'U8',
    's16le': 'S16_LE',
    's16be': 'S16_BE',
    'u16le': 'U16_LE',
    'u16be': 'U16_BE',
    's24le': 'S24_LE',
    's24be': 'S24_BE',
    's32le': 'S32_LE',
    's32be': 'S32_BE',
    'float_le': 'FLOAT_LE',
    'float_be': 'FLOAT_BE',
}


def record_audio_sample(device: AudioDeviceOptions, path: str,
                        seconds: int = 3) -> AudioCommandResult:
    if not device.input:
        raise ValueError(f'audio device {device.name!r} has no input')
    seconds = _validate_seconds(seconds)
    output_path = _validate_path(path, 'path')
    command = [
        'arecord',
        '-D', device.input,
        '-f', _alsa_format(device.format),
        '-r', str(device.sample_rate),
        '-c', str(device.channels),
        '-d', str(seconds),
        '-t', 'wav',
        str(output_path),
    ]
    return _run_audio_command(command, timeout=seconds + 5)


def play_audio_sample(device: AudioDeviceOptions, path: str
                      ) -> AudioCommandResult:
    if not device.output:
        raise ValueError(f'audio device {device.name!r} has no output')
    input_path = _validate_path(path, 'path')
    command = ['aplay', '-D', device.output, str(input_path)]
    return _run_audio_command(command)


def _validate_seconds(seconds: int) -> int:
    seconds = int(seconds)
    if seconds <= 0:
        raise ValueError('seconds must be positive')
    if seconds > 60:
        raise ValueError('seconds must be no greater than 60')
    return seconds


def _validate_path(path: str, label: str) -> Path:
    if not path:
        raise ValueError(f'{label} is required')
    if not isinstance(path, str):
        raise ValueError(f'{label} must be a string')
    return Path(path)


def _alsa_format(format_: str) -> str:
    return _FORMAT_ALIASES.get(format_.lower(), format_.upper())


def _run_audio_command(command: list[str], *,
                       timeout: int | None = None) -> AudioCommandResult:
    completed = subprocess.run(
        command, capture_output=True, check=True, text=True, timeout=timeout)
    return AudioCommandResult(
        command, completed.returncode, completed.stdout, completed.stderr)
