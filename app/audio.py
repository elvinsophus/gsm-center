# -*- coding: utf-8 -*-

from __future__ import annotations

from os import environ
import shlex
import subprocess
import re
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


class AudioProbeResult(NamedTuple):
    sample_rate: int
    command: list[str]
    ok: bool
    return_code: int | None
    stdout: str
    stderr: str


class ALSAAudioEndpoint(NamedTuple):
    card_index: int
    card_id: str
    card_name: str
    device_index: int
    device_name: str
    stream_name: str
    alsa_device: str
    kind: str


class ALSAAudioCard(NamedTuple):
    index: int
    id: str
    name: str
    description: str
    inputs: list[ALSAAudioEndpoint]
    outputs: list[ALSAAudioEndpoint]


_ALSA_CARD_REGEX = re.compile(r'^\s*(\d+)\s+\[([^]]+)]:\s+(.+)$')
_ALSA_DEVICE_REGEX = re.compile(
    r'^card\s+(\d+):\s+([^[]+)\[([^]]+)],\s+device\s+(\d+):\s+'
    r'([^[]+)\[([^]]+)]')


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


def probe_audio_input(device: str, *, sample_rates: list[int] | tuple[int, ...],
                      channels: int = 1, format_: str = 's16le',
                      seconds: int = 1,
                      backend: str = 'ffmpeg') -> list[AudioProbeResult]:
    if not device:
        raise ValueError('input device is required')
    seconds = _validate_seconds(seconds)
    results = []
    for sample_rate in sample_rates:
        sample_rate = int(sample_rate)
        command = _probe_audio_input_command(
            backend, device, sample_rate, channels, format_, seconds)
        try:
            completed = subprocess.run(
                command, capture_output=True, check=False, text=True,
                timeout=seconds + 5)
        except subprocess.TimeoutExpired as e:
            results.append(AudioProbeResult(
                sample_rate, command, False, None,
                _subprocess_output_to_str(e.stdout),
                _subprocess_output_to_str(e.stderr) or 'timed out'))
        else:
            results.append(AudioProbeResult(
                sample_rate, command, completed.returncode == 0,
                completed.returncode, completed.stdout, completed.stderr))
    return results


def discover_alsa_audio_cards() -> list[ALSAAudioCard]:
    cards = _read_alsa_cards()
    inputs = _read_alsa_endpoints('input')
    outputs = _read_alsa_endpoints('output')
    indices = sorted(set(cards) | set(inputs) | set(outputs))
    return [
        ALSAAudioCard(
            index=i,
            id=cards.get(i, {}).get('id', ''),
            name=cards.get(i, {}).get('name', ''),
            description=cards.get(i, {}).get('description', ''),
            inputs=inputs.get(i, []),
            outputs=outputs.get(i, []),
        )
        for i in indices
    ]


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


def _ffmpeg_codec(format_: str) -> str:
    format_ = format_.lower()
    if format_ == 's16le':
        return 'pcm_s16le'
    if format_ == 's16be':
        return 'pcm_s16be'
    if format_ == 's32le':
        return 'pcm_s32le'
    if format_ == 's32be':
        return 'pcm_s32be'
    return f'pcm_{format_}'


def _probe_audio_input_command(
        backend: str, device: str, sample_rate: int, channels: int,
        format_: str, seconds: int) -> list[str]:
    backend = backend.lower()
    if backend == 'arecord':
        return [
            'arecord',
            '-D', device,
            '-f', _alsa_format(format_),
            '-r', str(sample_rate),
            '-c', str(channels),
            '-d', str(seconds),
            '-t', 'raw',
            '/dev/null',
        ]
    if backend == 'ffmpeg':
        return [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-f', 'alsa',
            '-acodec', _ffmpeg_codec(format_),
            '-ac', str(channels),
            '-ar', str(sample_rate),
            '-i', device,
            '-t', str(seconds),
            '-f', 'null',
            '-',
        ]
    raise ValueError(f'unsupported audio probe backend {backend!r}')


def _read_alsa_cards() -> dict[int, dict]:
    try:
        content = Path('/proc/asound/cards').read_text()
    except OSError:
        return {}
    cards = {}
    current = None
    for line in content.splitlines():
        if match := _ALSA_CARD_REGEX.match(line):
            index, card_id, name = match.groups()
            current = int(index)
            cards[current] = {
                'id': card_id.strip(),
                'name': name.strip(),
                'description': '',
            }
        elif current is not None and line.strip():
            cards[current]['description'] = line.strip()
            current = None
    return cards


def _read_alsa_endpoints(kind: str) -> dict[int, list[ALSAAudioEndpoint]]:
    command = ['arecord' if kind == 'input' else 'aplay', '-l']
    try:
        completed = subprocess.run(
            command, capture_output=True, check=False, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {}
    cards = _read_alsa_cards()
    endpoints: dict[int, list[ALSAAudioEndpoint]] = {}
    for line in completed.stdout.splitlines():
        if not (match := _ALSA_DEVICE_REGEX.match(line)):
            continue
        card_index, card_id, card_name, device_index, device_name, stream = (
            match.groups())
        card_index = int(card_index)
        device_index = int(device_index)
        card_info = cards.get(card_index, {})
        endpoints.setdefault(card_index, []).append(ALSAAudioEndpoint(
            card_index=card_index,
            card_id=card_info.get('id') or card_id.strip(),
            card_name=card_info.get('name') or card_name.strip(),
            device_index=device_index,
            device_name=device_name.strip(),
            stream_name=stream.strip(),
            alsa_device=f'plughw:{card_index},{device_index}',
            kind=kind,
        ))
    return endpoints


def _run_audio_command(command: list[str], *,
                       timeout: int | None = None) -> AudioCommandResult:
    completed = subprocess.run(
        command, capture_output=True, check=True, text=True, timeout=timeout)
    return AudioCommandResult(
        command, completed.returncode, completed.stdout, completed.stderr)


def _subprocess_output_to_str(output: str | bytes | None) -> str:
    if output is None:
        return ''
    if isinstance(output, bytes):
        return output.decode(errors='replace')
    return output


def _terminate_process(process: subprocess.Popen, timeout: int):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)
