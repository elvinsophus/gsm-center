# -*- coding: utf-8 -*-

# noinspection PyPep8
import click
from flask.cli import FlaskGroup


def create_app():
    from app import create_app as c
    return c()


@click.group(cls=FlaskGroup, create_app=create_app)
def cli():
    """This is a management script for the application."""


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


@cli.command()
@click.argument('port', required=False, default='')
def loop(port):
    from app.main import GSMCenter

    if port:
        c = GSMCenter(port)
        try:
            c.join()
        finally:
            c.close()
        return

    GSMCenter.loop_all()


@cli.command()
@click.argument('sender', required=False, default='')
@click.option('-n', '--count', type=int, default=10)
def list_sent_smss(sender, count):
    from app.main import GSMCenter
    for sms in GSMCenter.GSMStore(sender).list_sent_smss(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {sms.sender} -> {sms.recipient}',
            f'  {sms.content}',
            ''
        ]))


@cli.command()
@click.argument('recipient', required=False, default='')
@click.option('-n', '--count', type=int, default=10)
def list_received_smss(recipient, count):
    from app.main import GSMCenter
    for sms in GSMCenter.GSMStore(recipient).list_received_smss(limit=count):
        print('\n'.join([
            f'#{sms.id} | {sms.time} | ({sms.status.name})',
            f'  {sms.sender} -> {sms.recipient}',
            f'  {sms.content}',
            ''
        ]))


@cli.command()
@click.argument('own_number', required=False, default='')
@click.option('-n', '--count', type=int, default=10)
def list_smss(own_number, count):
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


@cli.command()
@click.argument('own_number', required=False, default='')
@click.option('-n', '--count', type=int, default=10)
def preview_sms_dialogs(own_number, count):
    from app.main import GSMCenter
    types = GSMCenter.SMSType
    for sms, count in GSMCenter.GSMStore(own_number).preview_dialogs(count):
        print('\n'.join([
            f'{sms.own_number} <-> {sms.other_number} ({count})',
            f'  {"->" if sms.type is types.SENT else "<-"} {sms.time}: '
            f'{sms.content}',
            ''
        ]))


@cli.command()
@click.argument('own_number')
@click.argument('other_number')
@click.option('-n', '--count', type=int, default=10)
def list_sms_dialog(own_number, other_number, count):
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


@cli.command()
@click.argument('own_number', required=False, default='')
@click.option('-n', '--count', type=int, default=10)
def list_phone_calls(own_number, count):
    from app.main import GSMCenter
    types = GSMCenter.PhoneCallType
    for call in GSMCenter.GSMStore(own_number).list_phone_calls(limit=count):
        direction = '->' if call.type is types.OUTGOING else '<-'
        print('\n'.join([
            f'#{call.id} | {call.time} | ({call.status.name})',
            f'  {call.own_number} {direction} {call.other_number}',
            ''
        ]))


@cli.command()
@click.argument('caller')
@click.argument('recipient')
def call(caller, recipient):
    from app.main import GSMCenter
    mid = GSMCenter.GSMStore.add_phone_call(caller, recipient)
    print(f'queued phone call #{mid}')


@cli.command()
@click.argument('call_id', type=int)
def answer_call(call_id):
    from app.main import GSMCenter
    if GSMCenter.GSMStore.request_phone_call_answer(call_id):
        print(f'queued answer request for phone call #{call_id}')
    else:
        raise click.ClickException(f'phone call #{call_id} is not ringing')


@cli.command()
@click.argument('call_id', type=int)
def hangup_call(call_id):
    from app.main import GSMCenter
    if GSMCenter.GSMStore.request_phone_call_hangup(call_id):
        print(f'queued hangup request for phone call #{call_id}')
    else:
        raise click.ClickException(f'phone call #{call_id} not found')


@cli.command()
def test():
    """For making sure the project is operable."""
    print('Hello world!')


if __name__ == '__main__':
    cli()
