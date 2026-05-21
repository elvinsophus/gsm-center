# -*- coding: utf-8 -*-

# noinspection PyPep8
import click
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


@cli.command(short_help='List sent SMS messages.')
@click.argument('sender', required=False, default='', metavar='[SENDER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_sent_smss(sender, count):
    """List sent SMS messages, optionally filtered by own SENDER number."""
    from app.main import GSMCenter
    for sms in GSMCenter.GSMStore(sender).list_sent_smss(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {sms.sender} -> {sms.recipient}',
            f'  {sms.content}',
            ''
        ]))


@cli.command(short_help='List received SMS messages.')
@click.argument('recipient', required=False, default='', metavar='[RECIPIENT]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_received_smss(recipient, count):
    """List received SMS messages, optionally filtered by own RECIPIENT."""
    from app.main import GSMCenter
    for sms in GSMCenter.GSMStore(recipient).list_received_smss(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {sms.sender} -> {sms.recipient}',
            f'  {sms.content}',
            ''
        ]))


@cli.command(short_help='List sent and received SMS messages.')
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of messages to show.')
def list_smss(own_number, count):
    """List all SMS messages, optionally filtered by own phone number."""
    from app.main import GSMCenter
    types = GSMCenter.SMSType
    for sms in GSMCenter.GSMStore(own_number).list_smss(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {sms.own_number} {"->" if sms.type is types.SENT else "<-"}'
            f' {sms.other_number}',
            f'  {sms.content}',
            ''
        ]))


@cli.command(short_help='Preview latest SMS dialogs.')
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of dialogs to show.')
def preview_sms_dialogs(own_number, count):
    """Preview latest conversation rows for an optional own number."""
    from app.main import GSMCenter
    types = GSMCenter.SMSType
    for sms, count in GSMCenter.GSMStore(own_number).preview_dialogs(count):
        print('\n'.join([
            f'{sms.own_number} <-> {sms.other_number} ({count})',
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
    from app.main import GSMCenter
    normalise_num = GSMCenter.normalise_number
    types = GSMCenter.SMSType
    print(f'{normalise_num(own_number)} <-> {normalise_num(other_number)}')
    print()
    for sms in GSMCenter.GSMStore(own_number).list_dialog(other_number, count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {"->" if sms.type is types.SENT else "<-"} {sms.time}: '
            f'{sms.content}',
            ''
        ]))


@cli.command(short_help='List phone call history.')
@click.argument('own_number', required=False, default='',
                metavar='[OWN_NUMBER]')
@click.option('-n', '--count', type=int, default=10, show_default=True,
              help='Maximum number of calls to show.')
def list_phone_calls(own_number, count):
    """List phone calls, optionally filtered by own phone number."""
    from app.main import GSMCenter
    types = GSMCenter.PhoneCallType
    for call in GSMCenter.GSMStore(own_number).list_phone_calls(limit=count):
        direction = '->' if call.type is types.OUTGOING else '<-'
        print('\n'.join([
            f'#{call.id} | {call.time} | ({call.status.name})',
            f'  {call.own_number} {direction} {call.other_number}',
            ''
        ]))


@cli.command(short_help='Queue an outgoing phone call.')
@click.argument('caller', metavar='CALLER')
@click.argument('recipient', metavar='RECIPIENT')
def call(caller, recipient):
    """Queue an outgoing phone call from CALLER to RECIPIENT."""
    from app.main import GSMCenter
    mid = GSMCenter.GSMStore.add_phone_call(caller, recipient)
    print(f'queued phone call #{mid}')


@cli.command(short_help='Queue an answer request for a call.')
@click.argument('call_id', type=int, metavar='CALL_ID')
def answer_call(call_id):
    """Queue an answer request for ringing phone call CALL_ID."""
    from app.main import GSMCenter
    if GSMCenter.GSMStore.request_phone_call_answer(call_id):
        print(f'queued answer request for phone call #{call_id}')
    else:
        raise click.ClickException(f'phone call #{call_id} is not ringing')


@cli.command(short_help='Queue a hangup request for a call.')
@click.argument('call_id', type=int, metavar='CALL_ID')
def hangup_call(call_id):
    """Queue a hangup request for non-terminal phone call CALL_ID."""
    from app.main import GSMCenter
    if GSMCenter.GSMStore.request_phone_call_hangup(call_id):
        print(f'queued hangup request for phone call #{call_id}')
    else:
        raise click.ClickException(f'phone call #{call_id} not found')


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


@cli.command(short_help='Run a tiny operability check.')
def test():
    """For making sure the project is operable."""
    print('Hello world!')


if __name__ == '__main__':
    cli()
