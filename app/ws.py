# -*- coding: utf-8 -*-

from collections import defaultdict
from subprocess import PIPE, Popen
from threading import Event, Lock, Thread

from flask import Blueprint, request
from simple_websocket import ConnectionClosed, Server

from .audio import pcm_frame_bytes, play_pcm_command, record_pcm_command
from .main import (AudioDeviceOptions, DeviceOptions, GSMStore,
                   PhoneCallStatus)


bp = Blueprint('ws', __name__)
_output_locks: defaultdict[str, Lock] = defaultdict(Lock)


@bp.route('/ws/audio/devices/<name>/input')
def stream_audio_input(name):
    if not (device := AudioDeviceOptions.get(name)):
        return f'audio device {name!r} not found', 404
    return _accept_audio_ws(lambda ws: _stream_input(ws, device))


@bp.route('/ws/audio/devices/<name>/output')
def stream_audio_output(name):
    if not (device := AudioDeviceOptions.get(name)):
        return f'audio device {name!r} not found', 404
    return _accept_audio_ws(lambda ws: _stream_output(ws, device))


@bp.route('/ws/audio/devices/<name>/duplex')
def stream_audio_duplex(name):
    if not (device := AudioDeviceOptions.get(name)):
        return f'audio device {name!r} not found', 404
    return _accept_audio_ws(lambda ws: _stream_duplex(ws, device))


@bp.route('/ws/calls/<int:call_id>/audio')
def stream_call_audio(call_id):
    call = GSMStore('').get_phone_call(call_id)
    if call is None:
        return f'call #{call_id} not found', 404
    if call.status not in (
            PhoneCallStatus.ANSWERED,
            PhoneCallStatus.HANGUP_REQUESTED):
        return f'call #{call_id} is not answered', 409

    options = _device_options_for_own_number(call.own_number)
    if not options or not options.audio_device:
        return f'call #{call_id} has no configured audio device', 404
    if not (device := AudioDeviceOptions.get(options.audio_device)):
        return f'audio device {options.audio_device!r} not found', 404
    return _accept_audio_ws(lambda ws: _stream_duplex(ws, device))


def _accept_audio_ws(handler):
    try:
        ws = Server.accept(request.environ)
    except Exception as e:
        return f'websocket upgrade failed: {e}', 400
    try:
        handler(ws)
    except ConnectionClosed:
        pass
    return ''


def _device_options_for_own_number(own_number: str) -> DeviceOptions | None:
    for options in DeviceOptions.list().values():
        if options.own_number == own_number:
            return options
    return None


def _stream_input(ws: Server, device: AudioDeviceOptions):
    process = Popen(record_pcm_command(device), stdout=PIPE, stderr=PIPE)
    try:
        frame_size = pcm_frame_bytes(device)
        while process.poll() is None:
            chunk = process.stdout.read(frame_size)
            if not chunk:
                break
            ws.send(chunk)
    finally:
        _terminate_process(process)


def _stream_output(ws: Server, device: AudioDeviceOptions):
    lock = _output_locks[device.name]
    if not lock.acquire(blocking=False):
        ws.close(reason='audio output already has an owner')
        return
    process = Popen(play_pcm_command(device), stdin=PIPE, stderr=PIPE)
    try:
        while process.poll() is None:
            message = ws.receive()
            if message is None:
                break
            if isinstance(message, str):
                message = message.encode()
            process.stdin.write(message)
            process.stdin.flush()
    finally:
        lock.release()
        _terminate_process(process)


def _stream_duplex(ws: Server, device: AudioDeviceOptions):
    stop = Event()
    input_process = {}
    input_thread = Thread(
        target=_stream_input_until_stopped,
        args=(ws, device, stop, input_process))
    input_thread.start()
    try:
        _stream_output(ws, device)
    finally:
        stop.set()
        if process := input_process.get('process'):
            _terminate_process(process)
        input_thread.join(timeout=3)


def _stream_input_until_stopped(ws: Server, device: AudioDeviceOptions,
                                stop: Event, process_holder: dict):
    process = Popen(record_pcm_command(device), stdout=PIPE, stderr=PIPE)
    process_holder['process'] = process
    try:
        frame_size = pcm_frame_bytes(device)
        while not stop.is_set() and process.poll() is None:
            chunk = process.stdout.read(frame_size)
            if not chunk:
                break
            ws.send(chunk)
    except ConnectionClosed:
        stop.set()
    finally:
        _terminate_process(process)


def _terminate_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except Exception:
        process.kill()
        process.wait(timeout=3)


def init_app(app):
    app.register_blueprint(bp, url_prefix='')
