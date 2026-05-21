# -*- coding: utf-8 -*-

from flask import Flask, Blueprint, request, jsonify
from subprocess import CalledProcessError, TimeoutExpired
from .audio import (AudioCommandResult, play_audio_sample,
                    record_audio_sample)
from .main import (AudioDeviceOptions, GSMStore, PhoneCallStatus,
                   PhoneCallType, StoredPhoneCall)


bp = Blueprint('index', __name__)


@bp.route('/own-numbers', methods=['GET'])
def list_senders():
    return jsonify(GSMStore.list_active_own_numbers())


@bp.route('/audio/devices', methods=['GET'])
def list_audio_devices():
    return jsonify({
        name: _audio_device_to_json(device)
        for name, device in AudioDeviceOptions.list().items()
    })


@bp.route('/audio/devices/<name>', methods=['GET'])
def get_audio_device(name):
    if not (device := AudioDeviceOptions.get(name)):
        return f'audio device {name!r} not found', 404
    return jsonify(_audio_device_to_json(device))


@bp.route('/audio/devices/<name>/test-record', methods=['POST'])
def test_record_audio_device(name):
    if not (device := AudioDeviceOptions.get(name)):
        return f'audio device {name!r} not found', 404
    if not (args := request.json):
        return 'invalid argument', 400
    if not isinstance(args, dict):
        return 'invalid argument', 400
    try:
        result = record_audio_sample(
            device, args.get('path'), int(args.get('seconds', 3)))
    except (TypeError, ValueError) as e:
        return str(e), 400
    except (CalledProcessError, TimeoutExpired, OSError) as e:
        return str(e), 500
    return jsonify(_audio_command_result_to_json(result))


@bp.route('/audio/devices/<name>/test-play', methods=['POST'])
def test_play_audio_device(name):
    if not (device := AudioDeviceOptions.get(name)):
        return f'audio device {name!r} not found', 404
    if not (args := request.json):
        return 'invalid argument', 400
    if not isinstance(args, dict):
        return 'invalid argument', 400
    try:
        result = play_audio_sample(device, args.get('path'))
    except (TypeError, ValueError) as e:
        return str(e), 400
    except (CalledProcessError, TimeoutExpired, OSError) as e:
        return str(e), 500
    return jsonify(_audio_command_result_to_json(result))


@bp.route('/sms', methods=['POST'])
def update_record():
    if not (args := request.json):
        return 'invalid argument', 400
    if not isinstance(args, dict):
        return 'invalid argument', 400
    if not (sender := args.get('sender')):
        return 'parameter `sender` not provided', 400
    if not (recipient := args.get('recipient')):
        return 'parameter `recipient` not provided', 400
    if not (content := args.get('content')):
        return 'parameter `content` not provided', 400

    sender: str
    recipient: str
    content: str
    try:
        mid = GSMStore.add_pending_sms(sender, recipient, content)
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        return str(e), 500
    return jsonify(dict(id=mid))


@bp.route('/calls', methods=['POST'])
def add_call():
    if not (args := request.json):
        return 'invalid argument', 400
    if not isinstance(args, dict):
        return 'invalid argument', 400
    if not (caller := args.get('caller')):
        return 'parameter `caller` not provided', 400
    if not (recipient := args.get('recipient')):
        return 'parameter `recipient` not provided', 400

    caller: str
    recipient: str
    try:
        mid = GSMStore.add_phone_call(caller, recipient)
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        return str(e), 500
    return jsonify(dict(id=mid))


@bp.route('/calls', methods=['GET'])
def list_calls():
    try:
        own_number = request.args.get('own_number', '')
        other_number = request.args.get('other_number', '')
        limit = int(request.args.get('limit', 10))
        type_ = _enum_arg(PhoneCallType, request.args.get('type'))
        status = _enum_arg(PhoneCallStatus, request.args.get('status'))
        calls = GSMStore(own_number).list_phone_calls(
            type_, other_number=other_number, status=status, limit=limit)
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        return str(e), 500
    return jsonify([_phone_call_to_json(c) for c in calls])


@bp.route('/calls/<int:call_id>', methods=['GET'])
def get_call(call_id):
    try:
        if not (call := GSMStore('').get_phone_call(call_id)):
            return f'call #{call_id} not found', 404
    except Exception as e:
        return str(e), 500
    return jsonify(_phone_call_to_json(call))


@bp.route('/calls/<int:call_id>/answer', methods=['POST'])
def answer_call(call_id):
    try:
        if not GSMStore.request_phone_call_answer(call_id):
            return f'call #{call_id} is not ringing', 404
    except Exception as e:
        return str(e), 500
    return jsonify(dict(id=call_id, status='ANSWER_REQUESTED'))


@bp.route('/calls/<int:call_id>/hangup', methods=['POST'])
def hangup_call(call_id):
    try:
        if not GSMStore.request_phone_call_hangup(call_id):
            return f'call #{call_id} not found', 404
    except Exception as e:
        return str(e), 500
    return jsonify(dict(id=call_id, status='HANGUP_REQUESTED'))


def _enum_arg(enum_cls, value: str | None):
    if not value:
        return None
    try:
        return getattr(enum_cls, value.upper())
    except AttributeError:
        raise ValueError(f'invalid {enum_cls.__name__}: {value!r}')


def _datetime_to_timestamp(value):
    return int(value.timestamp()) if value else None


def _audio_device_to_json(device: AudioDeviceOptions) -> dict:
    return dict(
        name=device.name,
        input=device.input,
        output=device.output,
        sample_rate=device.sample_rate,
        channels=device.channels,
        format=device.format,
        frame_ms=device.frame_ms,
    )


def _audio_command_result_to_json(result: AudioCommandResult) -> dict:
    return dict(
        command=result.command,
        return_code=result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _phone_call_to_json(call: StoredPhoneCall) -> dict:
    return dict(
        id=call.id,
        type=call.type.name,
        time=_datetime_to_timestamp(call.time),
        own_number=call.own_number,
        other_number=call.other_number,
        caller=call.caller,
        recipient=call.recipient,
        status=call.status.name,
        started_at=_datetime_to_timestamp(call.started_at),
        ended_at=_datetime_to_timestamp(call.ended_at),
        extra=call.extra,
    )


def init_app(app: Flask):
    app.register_blueprint(bp, url_prefix='')
