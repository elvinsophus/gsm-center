# -*- coding: utf-8 -*-

from __future__ import annotations

from os import environ
import shlex
import subprocess
from pathlib import Path
from typing import NamedTuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .main import AudioDeviceOptions


class AudioCommandResult(NamedTuple):
    command: list[str]
    return_code: int
    stdout: str
    stderr: str


class AudioPipeline(NamedTuple):
    source: subprocess.Popen | None
    sink: subprocess.Popen


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

_FORMAT_SAMPLE_WIDTHS = {
    's8': 1,
    'u8': 1,
    's16le': 2,
    's16be': 2,
    'u16le': 2,
    'u16be': 2,
    's24le': 3,
    's24be': 3,
    's32le': 4,
    's32be': 4,
    'float_le': 4,
    'float_be': 4,
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


def record_pcm_command(device: AudioDeviceOptions) -> list[str]:
    if not device.input:
        raise ValueError(f'audio device {device.name!r} has no input')
    return [
        'arecord',
        '-D', device.input,
        '-f', _alsa_format(device.format),
        '-r', str(device.sample_rate),
        '-c', str(device.channels),
        '-t', 'raw',
    ]


def play_pcm_command(device: AudioDeviceOptions) -> list[str]:
    if not device.output:
        raise ValueError(f'audio device {device.name!r} has no output')
    return [
        'aplay',
        '-D', device.output,
        '-f', _alsa_format(device.format),
        '-r', str(device.sample_rate),
        '-c', str(device.channels),
        '-t', 'raw',
    ]


def pcm_frame_bytes(device: AudioDeviceOptions) -> int:
    sample_width = _FORMAT_SAMPLE_WIDTHS.get(device.format.lower())
    if sample_width is None:
        raise ValueError(f'unsupported audio format {device.format!r}')
    if device.sample_rate <= 0:
        raise ValueError('sample_rate must be positive')
    if device.channels <= 0:
        raise ValueError('channels must be positive')
    if device.frame_ms <= 0:
        raise ValueError('frame_ms must be positive')
    size = device.sample_rate * device.channels * sample_width
    return max(1, size * device.frame_ms // 1000)


def start_audio_input_command(
        device: AudioDeviceOptions, command: str, *,
        env: dict | None = None) -> AudioPipeline:
    if not command:
        raise ValueError('command is required')
    source = subprocess.Popen(
        record_pcm_command(device), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True)
    sink = subprocess.Popen(
        shlex.split(command), stdin=source.stdout,
        env={**environ, **(env or {})}, start_new_session=True)
    if source.stdout:
        source.stdout.close()
    return AudioPipeline(source, sink)


def start_audio_output_command(
        device: AudioDeviceOptions, command: str, *,
        env: dict | None = None) -> AudioPipeline:
    if not command:
        raise ValueError('command is required')
    source = subprocess.Popen(
        shlex.split(command), stdout=subprocess.PIPE,
        env={**environ, **(env or {})}, start_new_session=True)
    sink = subprocess.Popen(
        play_pcm_command(device), stdin=source.stdout,
        stderr=subprocess.PIPE, start_new_session=True)
    if source.stdout:
        source.stdout.close()
    return AudioPipeline(source, sink)


def stop_audio_pipeline(pipeline: AudioPipeline, *, timeout: int = 5
                        ) -> tuple[int | None, int | None]:
    for process in (pipeline.source, pipeline.sink):
        if process is not None:
            _terminate_process(process, timeout)
    source_code = pipeline.source.returncode if pipeline.source else None
    return source_code, pipeline.sink.returncode


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


def _terminate_process(process: subprocess.Popen, timeout: int):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)
