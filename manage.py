# -*- coding: utf-8 -*-

# noinspection PyPep8
import click
import json
from datetime import datetime
from flask.cli import FlaskGroup


def create_app():
    from app import create_app as c
    return c()


@click.group(cls=FlaskGroup, create_app=create_app)
def cli():
    """Manage GSM modem loops, SMS/call history, and audio smoke tests."""


@cli.command(
    short_help="Run an IPython shell in current_app context with some "
               "pre-imported modules.")
def shell():
    """Overwrites default shell command with IPython support."""
    import sys
    import IPython
    from traitlets.config import Config
    from flask import current_app

    c = Config()
    c.InteractiveShellEmbed.colors = 'linux'
    c.InteractiveShell.banner1 = '\n'.join([
        '=' * 64,
        f'Python {sys.version.splitlines()[0].strip()} on {sys.platform}',
        f'IPython: {IPython.__version__}',
        f'App: {current_app.import_name} [debug={current_app.debug}]',
        f'Instance: {current_app.instance_path}'
    ])
    c.InteractiveShellApp.exec_lines = [
        'print("\\n")',
        'def print_and_exec(cmd): print(cmd); exec(cmd, globals())',
        'print_and_exec("from app.main import GSMCenter")',
        'print_and_exec("from app.config import config")',
        'print_and_exec("from app.db import SIMCardDB, PendingSMSDB, SmsDB, PhoneCallDB")',
        'print_and_exec("from app.utils import *")',
        'print_and_exec("from functools import *")',
        'print_and_exec("from itertools import *")',
        'print_and_exec("from collections import *")',
        'print_and_exec("from decimal import *")',
        'print_and_exec("from datetime import datetime, date, timedelta")',
        'print_and_exec("import sys, os, re, time")',
        'print_and_exec("from flask import current_app, g")',
        'print_and_exec("g.lang = \'en_US\'")',
        'del print_and_exec'
    ]
    c.InteractiveShell.confirm_exit = False

    IPython.start_ipython(
        argv=(),
        user_ns=current_app.make_shell_context(),
        config=c,
    )


@cli.command(short_help='Run the modem listener loop.')
@click.argument('port', required=False, default='', metavar='[PORT]')
def loop(port):
    """Run the GSM modem listener for one serial PORT, or all devices."""
    from app.main import GSMCenter

    if port:
        c = GSMCenter(port)
        try:
            c.join()
        finally:
            c.close()
        return

    GSMCenter.loop_all()


@cli.command('list-contacts', short_help='List contact aliases.')
def list_contacts():
    """List configured contact aliases from the contact table."""
    from app.main import GSMCenter
    for alias, phone_number in GSMCenter.ContactBook.list().items():
        print(f'{alias}: {phone_number}')


@cli.command('set-contact', short_help='Create or update a contact alias.')
@click.argument('alias', metavar='ALIAS')
@click.argument('phone_number', metavar='PHONE_NUMBER')
def set_contact(alias, phone_number):
    """Create or update contact ALIAS for PHONE_NUMBER."""
    from app.main import GSMCenter
    GSMCenter.ContactBook.upsert(alias, phone_number)
    print(f'set contact {alias}: {GSMCenter.resolve_phone_number(alias)}')


@cli.command('delete-contact', short_help='Delete a contact alias.')
@click.argument('alias', metavar='ALIAS')
def delete_contact(alias):
    """Delete contact ALIAS."""
    from app.main import GSMCenter
    if not GSMCenter.ContactBook.delete(alias):
        raise click.ClickException(f'contact alias {alias!r} not found')
    print(f'deleted contact {alias}')


def _list_sent_smses(sender, count):
    from app.main import GSMCenter, format_contact_number
    for sms in GSMCenter.GSMStore(sender).list_sent_smses(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {format_contact_number(sms.sender)} -> '
            f'{format_contact_number(sms.recipient)}',
            f'  {sms.content}',
            ''
        ]))


@cli.command('list-sent-smses', short_help='List sent SMS messages.')
@click.argument('sender', required=False, default='', metavar='[SENDER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_sent_smses(sender, count):
    """List sent SMS messages, optionally filtered by own SENDER number."""
    _list_sent_smses(sender, count)


@cli.command('list-sent-smss', hidden=True)
@click.argument('sender', required=False, default='', metavar='[SENDER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_sent_smss(sender, count):
    """Legacy alias for list-sent-smses."""
    _list_sent_smses(sender, count)


def _list_received_smses(recipient, count):
    from app.main import GSMCenter, format_contact_number
    for sms in GSMCenter.GSMStore(recipient).list_received_smses(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {format_contact_number(sms.sender)} -> '
            f'{format_contact_number(sms.recipient)}',
            f'  {sms.content}',
            ''
        ]))


@cli.command('list-received-smses', short_help='List received SMS messages.')
@click.argument('recipient', required=False, default='', metavar='[RECIPIENT]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_received_smses(recipient, count):
    """List received SMS messages, optionally filtered by own RECIPIENT."""
    _list_received_smses(recipient, count)


@cli.command('list-received-smss', hidden=True)
@click.argument('recipient', required=False, default='', metavar='[RECIPIENT]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_received_smss(recipient, count):
    """Legacy alias for list-received-smses."""
    _list_received_smses(recipient, count)


def _list_smses(own_number, count):
    from app.main import GSMCenter, format_contact_number
    types = GSMCenter.SMSType
    for sms in GSMCenter.GSMStore(own_number).list_smses(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {format_contact_number(sms.own_number)} '
            f'{"->" if sms.type is types.SENT else "<-"} '
            f'{format_contact_number(sms.other_number)}',
            f'  {sms.content}',
            ''
        ]))


@cli.command('list-smses', short_help='List sent and received SMS messages.')
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_smses(own_number, count):
    """List all SMS messages, optionally filtered by own phone number."""
    _list_smses(own_number, count)


@cli.command('list-smss', hidden=True)
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_smss(own_number, count):
    """Legacy alias for list-smses."""
    _list_smses(own_number, count)


@cli.command(short_help='Preview latest SMS dialogs.')
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of dialogs to show.')
def preview_sms_dialogs(own_number, count):
    """Preview latest conversation rows for an optional own number."""
    from app.main import GSMCenter, format_contact_number
    types = GSMCenter.SMSType
    for sms, count in GSMCenter.GSMStore(own_number).preview_dialogs(count):
        print('\n'.join([
            f'{format_contact_number(sms.own_number)} <-> '
            f'{format_contact_number(sms.other_number)} ({count})',
            f'  {"->" if sms.type is types.SENT else "<-"} {sms.time}: '
            f'{sms.content}',
            ''
        ]))


@cli.command(short_help='List one SMS conversation.')
@click.argument('own_number', metavar='OWN_NUMBER')
@click.argument('other_number', metavar='OTHER_NUMBER')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_sms_dialog(own_number, other_number, count):
    """List the SMS dialog between OWN_NUMBER and OTHER_NUMBER."""
    from app.main import GSMCenter, format_contact_number
    resolve_num = GSMCenter.resolve_phone_number
    types = GSMCenter.SMSType
    print(
        f'{format_contact_number(resolve_num(own_number))} <-> '
        f'{format_contact_number(resolve_num(other_number))}')
    print()
    for sms in GSMCenter.GSMStore(own_number).list_dialog(other_number, count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {"->" if sms.type is types.SENT else "<-"} {sms.time}: '
            f'{sms.content}',
            ''
        ]))


def _list_calls(own_number, count):
    from app.main import GSMCenter, format_contact_number
    types = GSMCenter.PhoneCallType
    for phone_call in GSMCenter.GSMStore(
            own_number).list_phone_calls(limit=count):
        direction = '->' if phone_call.type is types.OUTGOING else '<-'
        started_at = phone_call.started_at or '-'
        ended_at = phone_call.ended_at or '-'
        duration = _format_duration(
            phone_call.started_at, phone_call.ended_at)
        extra = json.dumps(
            phone_call.extra, ensure_ascii=False, sort_keys=True
        ) if phone_call.extra else '{}'
        ended_by = _format_call_ended_by(phone_call, types)
        print('\n'.join([
            f'#{phone_call.id} | {phone_call.time} | '
            f'{phone_call.type.name} | {phone_call.status.name}',
            f'  {format_contact_number(phone_call.own_number)} {direction} '
            f'{format_contact_number(phone_call.other_number)}',
            f'  caller: '
            f'{format_contact_number(phone_call.caller) or "(unknown)"}',
            f'  recipient: '
            f'{format_contact_number(phone_call.recipient) or "(unknown)"}',
            f'  started_at: {started_at}',
            f'  ended_at: {ended_at}',
            f'  duration: {duration}',
            f'  ended_by: {ended_by}',
            f'  extra: {extra}',
            ''
        ]))


@cli.command('list-calls', short_help='List call history.')
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of calls to show.')
def list_calls(own_number, count):
    """List calls, optionally filtered by own phone number."""
    _list_calls(own_number, count)


@cli.command(short_help='Queue an outgoing phone call.')
@click.argument('caller', metavar='CALLER')
@click.argument('recipient', metavar='RECIPIENT')
def call(caller, recipient):
    """Queue an outgoing phone call from CALLER to RECIPIENT."""
    from app.main import GSMCenter
    mid = GSMCenter.GSMStore.add_phone_call(caller, recipient)
    print(f'queued phone call #{mid}')


@cli.command(short_help='Queue an answer request for a call.')
@click.argument('call_id', type=int, required=False, metavar='[CALL_ID]')
def answer_call(call_id):
    """Queue an answer request for CALL_ID, or the only ringing call."""
    from app.main import GSMCenter
    if call_id is None:
        call_id = _resolve_single_call_id(
            GSMCenter, [GSMCenter.PhoneCallStatus.RINGING], 'answer')
    if GSMCenter.GSMStore.request_phone_call_answer(call_id):
        print(f'queued answer request for phone call #{call_id}')
    else:
        raise click.ClickException(f'phone call #{call_id} is not ringing')


@cli.command(short_help='Queue a hangup request for a call.')
@click.argument('call_id', type=int, required=False, metavar='[CALL_ID]')
def hangup_call(call_id):
    """Queue a hangup request for CALL_ID, or the only active call.

    For a ringing incoming call, this rejects the call. Some carriers present
    rejection to the caller as busy.
    """
    from app.main import GSMCenter
    statuses = GSMCenter.PhoneCallStatus
    if call_id is None:
        call_id = _resolve_single_call_id(
            GSMCenter,
            [
                statuses.CREATED,
                statuses.DIALING,
                statuses.RINGING,
                statuses.ANSWER_REQUESTED,
                statuses.ANSWERED,
                statuses.HANGUP_REQUESTED,
            ],
            'hang up')
    if GSMCenter.GSMStore.request_phone_call_hangup(call_id):
        print(f'queued hangup request for phone call #{call_id}')
    else:
        raise click.ClickException(f'phone call #{call_id} not found')


def _resolve_single_call_id(gsm_center, statuses, action: str) -> int:
    store = gsm_center.GSMStore('')
    calls = []
    seen = set()
    for status in statuses:
        for phone_call in store.list_phone_calls(status=status, limit=100):
            if phone_call.id not in seen:
                calls.append(phone_call)
                seen.add(phone_call.id)
    if len(calls) == 1:
        return calls[0].id
    if not calls:
        raise click.ClickException(f'no phone call is available to {action}')
    ids = ', '.join(f'#{phone_call.id}' for phone_call in calls)
    raise click.ClickException(
        f'multiple phone calls are available to {action}: {ids}')


def _format_duration(started_at: datetime | None, ended_at: datetime | None):
    if not started_at:
        return '-'
    if not ended_at:
        return 'ongoing'
    seconds = max(0, int((ended_at - started_at).total_seconds()))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours:d}:{minutes:02d}:{seconds:02d}'
    return f'{minutes:d}:{seconds:02d}'


def _format_call_ended_by(phone_call, types):
    extra = phone_call.extra or {}
    if extra.get('ended_reason') == 'local_rejected':
        role = extra.get('ended_role') or (
            'dialee' if phone_call.type is types.INCOMING else 'caller')
        return f'rejected by local {role}'
    ended_by = extra.get('ended_by')
    role = extra.get('ended_role')
    if ended_by == 'local':
        return f'local {role}' if role else 'local'
    if ended_by == 'remote':
        return f'remote {role}' if role else 'remote'
    if extra.get('ended_reason') == 'remote_hangup_or_modem_cleared_call':
        role = 'dialee' if phone_call.type is types.OUTGOING else 'caller'
        return f'remote {role} or modem'
    return '-'


@cli.command(short_help='List configured audio devices.')
def list_audio_devices():
    """List top-level AUDIO_DEVICES entries from config.yaml."""
    from app.main import GSMCenter
    for name, device in GSMCenter.AudioDeviceOptions.list().items():
        print('\n'.join([
            name,
            f'  input: {device.input}',
            f'  output: {device.output}',
            f'  sample_rate: {device.sample_rate}',
            f'  channels: {device.channels}',
            f'  format: {device.format}',
            f'  frame_ms: {device.frame_ms}',
            ''
        ]))


@cli.command(short_help='Record a short audio sample.')
@click.argument('name', metavar='NAME')
@click.argument('path', metavar='PATH')
@click.option('--seconds', type=int, default=3, show_default=True,
              help='Number of seconds to record, from 1 to 60.')
def test_audio_record(name, path, seconds):
    """Record WAV audio from configured audio device NAME to PATH.

    NAME is a key under AUDIO_DEVICES in config.yaml, such as gsm_usb.
    PATH is the output WAV file path to create.
    """
    from app.audio import record_audio_sample
    from app.main import GSMCenter
    if not (device := GSMCenter.AudioDeviceOptions.get(name)):
        raise click.ClickException(f'audio device {name!r} not found')
    try:
        result = record_audio_sample(device, path, seconds)
    except Exception as e:
        raise click.ClickException(str(e))
    print(f'recorded audio sample to {path}')
    print(' '.join(result.command))


@cli.command(short_help='Play an audio sample.')
@click.argument('name', metavar='NAME')
@click.argument('path', metavar='PATH')
def test_audio_play(name, path):
    """Play WAV audio from PATH through configured audio device NAME.

    NAME is a key under AUDIO_DEVICES in config.yaml, such as gsm_usb.
    PATH is the input WAV file path to play.
    """
    from app.audio import play_audio_sample
    from app.main import GSMCenter
    if not (device := GSMCenter.AudioDeviceOptions.get(name)):
        raise click.ClickException(f'audio device {name!r} not found')
    try:
        result = play_audio_sample(device, path)
    except Exception as e:
        raise click.ClickException(str(e))
    print(f'played audio sample from {path}')
    print(' '.join(result.command))


@cli.command(short_help='Probe an ALSA input device and suggest config.')
@click.argument('name', required=False, default='audio_device',
                metavar='[NAME]')
@click.option('--input', 'input_', default='', metavar='ALSA_DEVICE',
              help='ALSA capture device to probe, e.g. plughw:3,0.')
@click.option('--output', default='', metavar='ALSA_DEVICE',
              help='ALSA playback device to include in the suggestion.')
@click.option('--rates', default='8000,16000,44100,48000',
              show_default=True,
              help='Comma-separated sample rates to test.')
@click.option('--channels', type=int, default=1, show_default=True,
              help='Number of capture channels to test.')
@click.option('--format', 'format_', default='s16le', show_default=True,
              help='PCM sample format to test.')
@click.option('--backend', type=click.Choice(['ffmpeg', 'arecord']),
              default='ffmpeg', show_default=True,
              help='Capture backend to probe.')
def probe_audio_device(name, input_, output, rates, channels, format_, backend):
    """Probe capture rates and print a suggested AUDIO_DEVICES block.

    NAME is only the AUDIO_DEVICES key to suggest, such as gsm_usb. It does not
    need to exist in config.yaml. If --input is omitted and NAME already exists,
    the configured input is probed.
    """
    from app.audio import probe_audio_input
    from app.main import GSMCenter

    configured = GSMCenter.AudioDeviceOptions.get(name)
    input_ = input_ or (configured.input if configured else '')
    output = output or (configured.output if configured else input_)
    if not input_:
        raise click.ClickException(
            'input device is required; pass --input or configure NAME')
    try:
        sample_rates = [int(r.strip()) for r in rates.split(',') if r.strip()]
    except ValueError:
        raise click.ClickException('rates must be comma-separated integers')
    if not sample_rates:
        raise click.ClickException('at least one sample rate is required')

    results = probe_audio_input(
        input_, sample_rates=sample_rates, channels=channels, format_=format_,
        backend=backend)
    for result in results:
        status = 'ok' if result.ok else 'failed'
        print(f'{result.sample_rate}: {status}')
        if not result.ok and result.stderr:
            print(f'  {result.stderr.strip().splitlines()[-1]}')

    supported = [result.sample_rate for result in results if result.ok]
    if not supported:
        raise click.ClickException('no tested sample rate worked')
    preferred = _preferred_audio_sample_rate(supported)
    print()
    print('Suggested AUDIO_DEVICES block:')
    print(f'  {name}:')
    print(f'    input: "{input_}"')
    print(f'    output: "{output}"')
    print(f'    sample_rate: {preferred}')
    print(f'    channels: {channels}')
    print(f'    format: {format_}')
    print('    frame_ms: 20')
    if backend == 'ffmpeg':
        print()
        print('Suggested recording command input flags:')
        print(f'  -f alsa -ac {channels} -ar {preferred} -i {input_}')


@cli.command(short_help='Discover ALSA sound cards for audio config.')
@click.option('--name', default='audio_device', show_default=True,
              help='AUDIO_DEVICES key to use in the suggested block.')
def discover_audio_devices(name):
    """List ALSA cards and suggest input/output device strings."""
    from app.audio import discover_alsa_audio_cards

    cards = discover_alsa_audio_cards()
    if not cards:
        raise click.ClickException('no ALSA audio cards found')
    recommended = _recommended_audio_card(cards)
    if recommended:
        print(
            f'recommended card: {recommended.index} '
            f'({recommended.id or recommended.name})')
        print()
    for card in cards:
        marker = '*' if recommended and card.index == recommended.index else ''
        print(
            f'card {card.index}{marker}: '
            f'{card.id or "-"} | {card.name or "-"}')
        if card.description:
            print(f'  {card.description}')
        if card.inputs:
            print('  inputs:')
            for endpoint in card.inputs:
                print(
                    f'    {endpoint.alsa_device} | '
                    f'{endpoint.device_name} [{endpoint.stream_name}]')
        else:
            print('  inputs: none')
        if card.outputs:
            print('  outputs:')
            for endpoint in card.outputs:
                print(
                    f'    {endpoint.alsa_device} | '
                    f'{endpoint.device_name} [{endpoint.stream_name}]')
        else:
            print('  outputs: none')
        if card.inputs or card.outputs:
            input_ = card.inputs[0].alsa_device if card.inputs else ''
            output = card.outputs[0].alsa_device if card.outputs else ''
            print('  suggested AUDIO_DEVICES block:')
            print(f'    {name}:')
            if input_:
                print(f'      input: "{input_}"')
            if output:
                print(f'      output: "{output}"')
            print('      sample_rate: 48000')
            print('      channels: 1')
            print('      format: s16le')
            print('      frame_ms: 20')
        print()


def _recommended_audio_card(cards):
    useful = [card for card in cards if card.inputs and card.outputs]
    if not useful:
        return None
    for card in useful:
        text = ' '.join([card.id, card.name, card.description]).lower()
        if 'usb' in text:
            return card
    return useful[0]


def _preferred_audio_sample_rate(sample_rates):
    for rate in (8000, 16000, 48000, 44100):
        if rate in sample_rates:
            return rate
    return sample_rates[0]


@cli.command(short_help='Run a tiny operability check.')
def test():
    """For making sure the project is operable."""
    print('Hello world!')


if __name__ == '__main__':
    cli()
