# -*- coding: utf-8 -*-

from functools import cached_property
from enum import Enum
from datetime import datetime
from time import time, sleep
from json import loads as json_loads
from threading import Thread
from sys import exc_info
from traceback import format_tb
from logging import getLogger
from typing import NamedTuple
from os import environ
from gsmmodem.modem import (GsmModem, TimeoutException as GSMTimeout,
                            IncomingCall, SentSms, ReceivedSms, StatusReport,
                            PinRequiredError, IncorrectPinError)
from .config import config
from .db import (SIMCardDB, PendingSMSDB, SmsDB, ReceivedSMSPartDB,
                 PhoneCallDB)
from .utils import timestamp_to_datetime, safe, run_system_command
import phonenumbers


SMSType = SmsDB.SMSType
PhoneCallType = PhoneCallDB.PhoneCallType
_EMPTY_ARG = object()


class PendingSMSStatus(Enum):
    CREATED = 0
    PENDING = 1
    PROCESSED = 2


class SentSMSStatus(Enum):
    PENDING = 0
    SENT = 1
    DELIVERED = 2
    FAILED = 3


class ReceivedSMSStatus(Enum):
    UNREAD = 0
    READ = 1


class ReceivedSMSPartStatus(Enum):
    RECEIVED = 0
    ASSEMBLED = 1


class PhoneCallStatus(Enum):
    CREATED = 0
    DIALING = 1
    RINGING = 2
    ANSWER_REQUESTED = 3
    ANSWERED = 4
    HANGUP_REQUESTED = 5
    ENDED = 6
    FAILED = 7


class PendingSMS(NamedTuple):
    id: int
    sender: str
    recipient: str
    content: str
    status: PendingSMSStatus


class StoredSMS(NamedTuple):
    id: int
    type: SMSType
    time: datetime
    own_number: str
    other_number: str
    content: str
    delivery_report: dict | None
    status: SentSMSStatus | ReceivedSMSStatus

    @property
    def sender(self) -> str:
        return (self.own_number if self.type is SMSType.SENT
                else self.other_number)

    @property
    def recipient(self) -> str:
        return (self.own_number if self.type is SMSType.RECEIVED
                else self.other_number)


class ReceivedSMSPartInfo(NamedTuple):
    reference: str
    total: int
    sequence: int
    raw_pdu: str | None = None
    encoding: str | None = None
    extra: dict | None = None


class StoredPhoneCall(NamedTuple):
    id: int
    type: PhoneCallType
    time: datetime
    own_number: str
    other_number: str
    status: PhoneCallStatus
    started_at: datetime | None
    ended_at: datetime | None
    extra: dict | None

    @property
    def caller(self) -> str:
        return (self.own_number if self.type is PhoneCallType.OUTGOING
                else self.other_number)

    @property
    def recipient(self) -> str:
        return (self.own_number if self.type is PhoneCallType.INCOMING
                else self.other_number)


class GSMStore:

    sim_card_db = SIMCardDB()
    pending_sms_db = PendingSMSDB()
    sms_db = SmsDB()
    received_sms_part_db = ReceivedSMSPartDB()
    phone_call_db = PhoneCallDB()

    def __init__(self, own_number: str):
        if own_number:
            own_number = GSMCenter.normalise_number(own_number)
        self._own_number = own_number

    def __repr__(self):
        return f'<{type(self).__name__}>'

    def get_pending_sms(self, mid: int) -> PendingSMS | None:
        if not (row := self.pending_sms_db.get(mid)):
            return None
        return self.pending_sms_from_db(row)

    def list_pending_smss(self, *,
                          status: PendingSMSStatus | None = None,
                          limit: int = 10) -> list[PendingSMS]:
        return list(map(
            self.pending_sms_from_db,
            self.pending_sms_db.list(
                self._own_number, status=status, limit=limit)
        ))

    @classmethod
    def pending_sms_from_db(cls, row: dict) -> PendingSMS:
        return PendingSMS(
            row['id'],
            row['sender'], row['recipient'], row['content'],
            getattr(PendingSMSStatus, row['status'])
        )

    def get_sms(self, mid: int) -> StoredSMS | None:
        if not (row := self.sms_db.get(mid)):
            return None
        return self.sms_from_db(row)

    def list_smss(self, type_: SMSType | None = None, *,
                  other_number: str | None = None,
                  status: SentSMSStatus | None = None,
                  limit: int = 10) -> list[StoredSMS]:
        if other_number:
            other_number = GSMCenter.normalise_number(other_number)
        return list(map(
            self.sms_from_db,
            self.sms_db.list(
                type_, self._own_number,
                other_number=other_number or '', status=status, limit=limit
            )
        ))

    @classmethod
    def sms_from_db(cls, row: dict) -> StoredSMS:
        return StoredSMS(
            row['id'], (type_ := getattr(SMSType, row['type'])),
            timestamp_to_datetime(row['created_at'] if type_ is SMSType.SENT
                                  else row['time']),
            row['own_number'], row['other_number'], row['content'],
            (json_loads(dr) if (dr := row['delivery_report']) else None),
            getattr((SentSMSStatus if type_ is SMSType.SENT
                     else ReceivedSMSStatus),
                    row['status'])
        )

    def get_sent_sms(self, mid: int) -> StoredSMS | None:
        if (sms := self.get_sms(mid)) is None:
            return None
        if sms.type is not SMSType.SENT:
            return None
        return sms

    def list_sent_smss(self, *,
                       recipient: str = '',
                       status: SentSMSStatus | None = None,
                       limit: int = 10
                       ) -> list[StoredSMS]:
        return self.list_smss(
            SMSType.SENT, other_number=recipient, status=status, limit=limit)

    def get_received_sms(self, mid: int) -> StoredSMS | None:
        if (sms := self.get_sms(mid)) is None:
            return None
        if sms.type is not SMSType.RECEIVED:
            return None
        return sms

    def list_received_smss(self, *,
                           sender: str | None = None,
                           status: SentSMSStatus | None = None,
                           limit: int = 10
                           ) -> list[StoredSMS]:
        return self.list_smss(
            SMSType.RECEIVED, other_number=sender, status=status, limit=limit)

    def preview_dialogs(self, limit: int = 10) -> list[tuple[StoredSMS, int]]:
        from_db = self.sms_from_db
        return [
            (from_db(row), row['id_count']) for row
            in self.sms_db.list_last_of_each(self._own_number, limit=limit)
        ]

    def list_dialog(self, other_number: str, limit: int = 10):
        return list(map(
            self.sms_from_db,
            self.sms_db.list(
                own_number=self._own_number,
                other_number=GSMCenter.normalise_number(other_number),
                limit=limit)
        ))

    def add_received_sms(self, sender: str, content: str,
                         status: ReceivedSMSStatus, time_: int,
                         part_info: ReceivedSMSPartInfo | None = None
                         ) -> int | None:
        if part_info is None:
            return self.sms_db.insert(
                SMSType.RECEIVED, self._own_number, sender, content, status,
                time_)

        self.received_sms_part_db.insert(
            self._own_number, sender, content,
            part_info.reference, part_info.total, part_info.sequence,
            ReceivedSMSPartStatus.RECEIVED, time_=time_,
            raw_pdu=part_info.raw_pdu, encoding=part_info.encoding,
            extra=part_info.extra)
        return self._assemble_received_sms_parts(
            sender, part_info.reference, status)

    def assemble_all_received_sms_parts(self) -> int:
        count = 0
        for group in self.received_sms_part_db.list_unassembled_groups():
            if group['own_number'] != self._own_number:
                continue
            if self._assemble_received_sms_parts(
                    group['other_number'], group['concat_reference'],
                    ReceivedSMSStatus.UNREAD) is not None:
                count += 1
        return count

    def _assemble_received_sms_parts(self, sender: str, reference: str,
                                     status: ReceivedSMSStatus
                                     ) -> int | None:
        part_db = self.received_sms_part_db
        parts = part_db.list_group(
            self._own_number, sender, reference,
            status=ReceivedSMSPartStatus.RECEIVED)
        if not parts:
            return None

        total = parts[0]['concat_total']
        sequences = {p['concat_sequence'] for p in parts}
        if len(parts) < total or sequences != set(range(1, total + 1)):
            return None

        content = ''.join(
            p['content'] for p in sorted(parts, key=lambda p: p[
                'concat_sequence']))
        timestamp = min((p['time'] for p in parts if p['time']), default=None)
        mid = self.sms_db.insert(
            SMSType.RECEIVED, self._own_number, sender, content, status,
            timestamp)
        if mid is None:
            raise RuntimeError('assembled SMS could not be inserted into DB')
        part_db.mark_group_assembled(
            self._own_number, sender, reference, mid,
            ReceivedSMSPartStatus.ASSEMBLED)
        return mid

    def get_phone_call(self, mid: int) -> StoredPhoneCall | None:
        if not (row := self.phone_call_db.get(mid)):
            return None
        return self.phone_call_from_db(row)

    def list_phone_calls(self,
                         type_: PhoneCallType | None = None, *,
                         other_number: str = '',
                         status: PhoneCallStatus | None = None,
                         limit: int = 10) -> list[StoredPhoneCall]:
        if other_number:
            other_number = GSMCenter.normalise_number(other_number)
        return list(map(
            self.phone_call_from_db,
            self.phone_call_db.list(
                type_, self._own_number,
                other_number=other_number, status=status, limit=limit)
        ))

    @classmethod
    def phone_call_from_db(cls, row: dict) -> StoredPhoneCall:
        started_at = row['started_at']
        ended_at = row['ended_at']
        return StoredPhoneCall(
            row['id'], getattr(PhoneCallType, row['type']),
            timestamp_to_datetime(row['created_at']),
            row['own_number'], row['other_number'],
            getattr(PhoneCallStatus, row['status']),
            (timestamp_to_datetime(started_at) if started_at else None),
            (timestamp_to_datetime(ended_at) if ended_at else None),
            (json_loads(extra) if (extra := row['extra']) else None)
        )

    @classmethod
    def list_active_own_numbers(cls, threshold: int = 60, *,
                                call_enabled: bool | None = None,
                                sms_enabled: bool | None = None) -> list[str]:
        return cls.sim_card_db.list_phone_numbers(
            int(time()) - threshold,
            call_enabled=call_enabled, sms_enabled=sms_enabled)

    @classmethod
    def add_pending_sms(cls, sender: str, recipient: str, content: str
                        ) -> int | None:
        sender = GSMCenter.normalise_number(sender)
        recipient = GSMCenter.normalise_number(recipient)
        threshold = 60
        if sender not in cls.list_active_own_numbers(threshold,
                                                     sms_enabled=True):
            raise ValueError(
                f'phone number {sender!r} cannot be used as sender '
                f'for it has not been active for more than {threshold}s')
        return cls.pending_sms_db.insert(
            sender, recipient, content, PendingSMSStatus.CREATED)

    @classmethod
    def add_phone_call(cls, caller: str, recipient: str) -> int | None:
        caller = GSMCenter.normalise_number(caller)
        recipient = GSMCenter.normalise_number(recipient)
        threshold = 60
        if caller not in cls.list_active_own_numbers(threshold,
                                                     call_enabled=True):
            raise ValueError(
                f'phone number {caller!r} cannot be used as caller '
                f'for it has not been active for more than {threshold}s')
        return cls.phone_call_db.insert(
            PhoneCallType.OUTGOING, caller, recipient, PhoneCallStatus.CREATED)

    @classmethod
    def request_phone_call_answer(cls, mid: int) -> bool:
        return cls.phone_call_db.update_status(
            mid, PhoneCallStatus.ANSWER_REQUESTED,
            from_status=PhoneCallStatus.RINGING)

    @classmethod
    def request_phone_call_hangup(cls, mid: int) -> bool:
        if not (row := cls.phone_call_db.get(mid)):
            return False
        status = getattr(PhoneCallStatus, row['status'])
        if status in (PhoneCallStatus.ENDED, PhoneCallStatus.FAILED):
            return False
        if status is PhoneCallStatus.HANGUP_REQUESTED:
            return True
        return cls.phone_call_db.update_status(
            mid, PhoneCallStatus.HANGUP_REQUESTED, from_status=status)


class DeviceOptions(NamedTuple):
    baud_rate: int = 115200
    pin: str = None
    own_number: str = None
    sms_enabled: bool = False
    call_enabled: bool = False
    audio_device: str = ''
    on_sms_received: str = ''
    on_sms_received_env: dict = None
    on_call_received: str = ''
    on_call_received_env: dict = None
    on_call_dialing: str = ''
    on_call_dialing_env: dict = None
    on_call_answered: str = ''
    on_call_answered_env: dict = None
    on_call_ended: str = ''
    on_call_ended_env: dict = None
    on_call_failed: str = ''
    on_call_failed_env: dict = None

    @classmethod
    def from_dict(cls, d: dict) -> 'DeviceOptions':
        args = {}
        if (baud_rate := d.get('baudrate', None)) is not None:
            baud_rate: str
            args['baud_rate'] = int(baud_rate)
        if pin := d.get('pin'):
            args['pin'] = str(pin)
        if own_number := d.get('own_number'):
            args['own_number'] = str(own_number)
        sms_conf = _dict_or_empty(d.get('sms'))
        call_conf = _dict_or_empty(d.get('calls'))
        sms_received = _dict_or_empty(sms_conf.get('on_received'))
        call_hooks = _dict_or_empty(call_conf.get('hooks'))

        if (sms_enabled := _first_defined(
                sms_conf.get('enabled'), d.get('sms_enabled'))) is not None:
            args['sms_enabled'] = bool(sms_enabled)
        if (call_enabled := _first_defined(
                call_conf.get('enabled'), d.get('call_enabled'))) is not None:
            args['call_enabled'] = bool(call_enabled)
        if audio_device := _first_truthy(
                call_conf.get('audio_device'), d.get('audio_device')):
            args['audio_device'] = str(audio_device)
        if on_sms_received := _first_truthy(
                sms_received.get('command'), d.get('on_sms_received')):
            args['on_sms_received'] = str(on_sms_received)
        if on_sms_received_env := _first_truthy(
                sms_received.get('env'), d.get('on_sms_received_env')):
            args['on_sms_received_env'] = on_sms_received_env
        for name in ('received', 'dialing', 'answered', 'ended', 'failed'):
            hook = _dict_or_empty(call_hooks.get(name))
            legacy_cmd = d.get(f'on_call_{name}')
            legacy_env = d.get(f'on_call_{name}_env')
            if cmd := _first_truthy(hook.get('command'), legacy_cmd):
                args[f'on_call_{name}'] = str(cmd)
            if env := _first_truthy(hook.get('env'), legacy_env):
                args[f'on_call_{name}_env'] = env
        return cls(**args)


class AudioDeviceOptions(NamedTuple):
    name: str
    input: str = ''
    output: str = ''
    sample_rate: int = 8000
    channels: int = 1
    format: str = 's16le'
    frame_ms: int = 20

    @classmethod
    def from_dict(cls, name: str, d: dict) -> 'AudioDeviceOptions':
        args: dict = {'name': str(name)}
        if input_ := d.get('input'):
            args['input'] = str(input_)
        if output := d.get('output'):
            args['output'] = str(output)
        if (sample_rate := d.get('sample_rate')) is not None:
            sample_rate: int | str
            args['sample_rate'] = int(sample_rate)
        if (channels := d.get('channels')) is not None:
            channels: int | str
            args['channels'] = int(channels)
        if format_ := d.get('format'):
            args['format'] = str(format_)
        if (frame_ms := d.get('frame_ms')) is not None:
            frame_ms: int | str
            args['frame_ms'] = int(frame_ms)
        return cls(**args)

    @classmethod
    def list(cls) -> dict[str, 'AudioDeviceOptions']:
        audio_confs = config.get('AUDIO_DEVICES') or {}
        return {
            name: cls.from_dict(name, _dict_or_empty(conf))
            for name, conf in audio_confs.items()
        }

    @classmethod
    def get(cls, name: str) -> 'AudioDeviceOptions | None':
        return cls.list().get(name)


def _dict_or_empty(value: dict | None) -> dict:
    return value if isinstance(value, dict) else {}


def _first_defined(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _first_truthy(*values):
    for value in values:
        if value:
            return value
    return None


def _sms_attrs(sms) -> dict:
    attrs = {}
    try:
        attrs.update(vars(sms))
    except TypeError:
        pass
    for name in dir(sms):
        if name.startswith('_') or name in attrs:
            continue
        try:
            value = getattr(sms, name)
        except Exception:
            continue
        if callable(value):
            continue
        attrs[name] = value
    return attrs


def _first_attr(attrs: dict, names: tuple[str, ...]):
    for name in names:
        if (value := attrs.get(name)) is not None:
            return value
    return None


def _first_int_attr(attrs: dict, names: tuple[str, ...]) -> int | None:
    value = _first_attr(attrs, names)
    if value is None:
        return None
    try:
        # noinspection PyTypeChecker
        return int(value)
    except (TypeError, ValueError):
        return None


def _bytes_from_udh(udh) -> bytes:
    if isinstance(udh, bytes):
        return udh
    if isinstance(udh, bytearray):
        return bytes(udh)
    if isinstance(udh, str):
        text = udh.replace(' ', '')
        try:
            return bytes.fromhex(text)
        except ValueError:
            return b''
    try:
        return bytes(udh)
    except (TypeError, ValueError):
        return b''


class GSMCenter:

    SMSType = SMSType
    GSMStore = GSMStore
    PendingSMS = PendingSMS
    PendingSMSStatus = PendingSMSStatus
    StoredSMS = StoredSMS
    SentSMSStatus = SentSMSStatus
    ReceivedSMSStatus = ReceivedSMSStatus
    ReceivedSMSPartInfo = ReceivedSMSPartInfo
    ReceivedSMSPartStatus = ReceivedSMSPartStatus
    PhoneCallType = PhoneCallType
    StoredPhoneCall = StoredPhoneCall
    PhoneCallStatus = PhoneCallStatus
    DeviceOptions = DeviceOptions
    AudioDeviceOptions = AudioDeviceOptions

    def __init__(self, port: str = '', **kwargs):
        dev_confs = config.get('DEVICES') or {}
        if not port:
            if not dev_confs:
                raise ValueError(f'`port` not given')
            port = next(iter(dev_confs))

        conf_ops = conf_ops.copy() if (conf_ops := dev_confs.get(port)) else {}
        conf_ops.update(kwargs)
        self._options = options \
            = DeviceOptions.from_dict(conf_ops)
        self._modem = GsmModem(
            port,
            options.baud_rate,
            incomingCallCallbackFunc=(self._handle_incoming_call
                                      if options.call_enabled else None),
            smsReceivedCallbackFunc=(self._handle_received_sms
                                     if options.sms_enabled else None),
            smsStatusReportCallback=self._handle_status_report
        )
        self._pin = options.pin
        self._own_number = ''
        self._is_alive = True
        self._active_calls = {}

        self._connect()
        self._own_number = self._check_own_number()
        self._store = GSMStore(self._own_number)
        self._assemble_stored_received_sms_parts()
        self._clear_stale_phone_calls()
        self.check_network_coverage()
        self._check_modem_stored_smss()
        self._loop_thread = loop_thread = Thread(target=self._loop)
        loop_thread.start()

        self.logger.info(f'initiation succeeded')

    def __repr__(self):
        return f'<{type(self).__name__} {self._modem.port}>'

    @classmethod
    def get_class_logger(cls):
        return getLogger(f'{cls.__module__}.{cls.__qualname__}')

    @cached_property
    def logger(self):
        return getLogger(f'{type(self).__module__}.{self!r}')

    def _init(self):
        self._connect()
        self._own_number = self._check_own_number()
        self._store = GSMStore(self._own_number)
        self._assemble_stored_received_sms_parts()
        self._clear_stale_phone_calls()
        self.check_network_coverage()
        self._check_modem_stored_smss()
        self._loop_thread = loop_thread = Thread(target=self._loop)
        loop_thread.start()

    def _connect(self, timeout: int = 10) -> bool:
        modem = self._modem
        if modem.alive:
            return True
        self.logger.info(f'connecting to MODEM...')
        try:
            modem.connect(self._pin, waitingForModemToStartInSeconds=timeout)
        except PinRequiredError:
            self.logger.error('SIM card PIN required.')
            return False
        except IncorrectPinError:
            self.logger.error('incorrect SIM card PIN.')
            return False
        except Exception as e:
            self.logger.error(f'connection failed due to {e!r}')
            return False
        self.logger.info(f'successfully connected to MODEM')
        return True

    def _check_own_number(self) -> str:
        if not self._connect():
            raise RuntimeError(f'MODEM is not connected')

        logger = self.logger
        normalise = self.normalise_number

        if conf_number := self._options.own_number:
            conf_number = normalise(conf_number)
        real_number: str | None
        # noinspection PyTypeChecker
        if real_number := self._modem.ownNumber:
            real_number = normalise(real_number)

        if not real_number:
            if not conf_number:
                raise RuntimeError(
                    f'cannot fetch own number; '
                    f'please provide it via config `DEVICES`')
            logger.info(
                f'cannot fetch own number; '
                f'using configured own number {conf_number!r}')
            return conf_number

        if conf_number:
            if conf_number != real_number:
                logger.warning(
                    f'overwriting real own number {real_number!r} '
                    f'with {conf_number!r}')
            return conf_number

        logger.info(f'own number is {real_number!r}')
        return real_number

    def set_modem_own_number(self, number: str):
        # This is not guaranteed to be supported by the MODEM.
        if not self._connect():
            raise RuntimeError(f'MODEM is not connected')
        self._modem.ownNumber = self.normalise_number(number)

    @classmethod
    def normalise_number(cls, number: str) -> str:
        try:
            parsed = phonenumbers.parse(
                number, region=config.get('DEFAULT_MOBILE_REGION'))
        except phonenumbers.NumberParseException:
            if number.isdigit():
                return number
            raise
        return f'+{parsed.country_code}{parsed.national_number}'

    @classmethod
    def simplify_number(cls, number: str) -> str:
        number = cls.normalise_number(number)
        if not (region := config.get('DEFAULT_MOBILE_REGION')):
            return number
        region: str
        if not (country_code := phonenumbers.country_code_for_region(region)):
            return number
        return number.removeprefix(f'+{country_code}')

    def _update_sim_card_status(self):
        if not self._connect():
            return
        options = self._options
        self._store.sim_card_db.update(
            self._modem.port, self._own_number,
            options.call_enabled, options.sms_enabled)

    def check_network_coverage(self, timeout: int = 5) -> int:
        # coverage: (0, 99]
        if not self._connect():
            return 0
        logger = self.logger
        logger.info('checking network coverage...')
        try:
            coverage = self._modem.waitForNetworkCoverage(timeout)
        except GSMTimeout:
            logger.error(f'network signal strength is insufficient '
                         f'(timeout {timeout!r} reached)')
            return 0
        logger.info(f'network coverage is {coverage}')
        return coverage

    def _check_modem_stored_smss(self):
        if not self._options.sms_enabled:
            return
        if not self._connect():
            return
        self.logger.info(f'processing SMSs stored in MODEM...')
        self._modem.processStoredSms()

    def _assemble_stored_received_sms_parts(self):
        if not self._options.sms_enabled:
            return
        count = self._store.assemble_all_received_sms_parts()
        if count:
            self.logger.info(
                f'assembled {count} stored multipart SMS message(s)')

    def _handle_incoming_call(self, call: IncomingCall):
        sender = self.normalise_number(call.number)
        self.logger.info(f'received a call from {sender!r}')
        mid = self._store.phone_call_db.insert(
            PhoneCallType.INCOMING, self._own_number, sender,
            PhoneCallStatus.RINGING)
        if mid is None:
            raise RuntimeError('incoming call could not be inserted into DB')
        self._active_calls[mid] = call
        self._run_call_hook(mid, 'received')

    def _clear_stale_phone_calls(self):
        if not self._options.call_enabled:
            return

        db = self._store.phone_call_db
        stale_statuses = (
            PhoneCallStatus.DIALING,
            PhoneCallStatus.RINGING,
            PhoneCallStatus.ANSWER_REQUESTED,
            PhoneCallStatus.ANSWERED,
            PhoneCallStatus.HANGUP_REQUESTED,
        )
        count = 0
        for status in stale_statuses:
            while rows := db.list(
                    own_number=self._own_number, status=status, limit=100):
                for row in rows:
                    if db.update_status(
                            row['id'], PhoneCallStatus.ENDED,
                            from_status=status, ended_at=int(time()),
                            extra=dict(
                                error='loop restarted while call was active')):
                        count += 1
        if count:
            self.logger.warning(
                f'marked {count} stale phone call(s) as ended')

    def make_phone_call(self, recipient: str, *,
                        wait_for_answer: bool | float = False
                        ) -> int | None:
        if not self._options.call_enabled:
            raise RuntimeError(f'phone calls are not enabled on this device')

        if self.check_network_coverage() <= 0:
            return None

        logger = self.logger
        recipient = self.normalise_number(recipient)
        call_db = self._store.phone_call_db
        statuses = PhoneCallStatus
        mid = call_db.insert(
            PhoneCallType.OUTGOING, self._own_number, recipient,
            statuses.DIALING)
        if mid is None:
            raise RuntimeError('phone call could not be inserted into DB')
        self._run_call_hook(mid, 'dialing')

        logger.info(f'making phone call #{mid} to {recipient!r}...')
        try:
            call = self._modem.dial(
                self.simplify_number(recipient),
                timeout=(30 if isinstance(wait_for_answer, bool)
                         else wait_for_answer),
                callStatusUpdateCallbackFunc=(
                    self._call_status_callback(mid)))
        except Exception as e:
            logger.error(f'phone call #{mid} failed due to {e!r}')
            self._update_phone_call_status(
                mid, statuses.FAILED, ended_at=int(time()),
                extra=dict(exc=repr(e), tb=format_tb(exc_info()[2])))
        else:
            self._active_calls[mid] = call
            status = statuses.ANSWERED if getattr(call, 'answered', False) \
                else statuses.DIALING
            self._update_phone_call_status(
                mid, status,
                started_at=(int(time()) if status is statuses.ANSWERED
                            else None))

        return mid

    def _call_status_callback(self, mid: int):
        def callback(call):
            self.logger.info(f'phone call #{mid} status updated: {call}')
            if getattr(call, 'answered', False):
                self._update_phone_call_status(
                    mid, PhoneCallStatus.ANSWERED, started_at=int(time()))
            if not getattr(call, 'active', True):
                self._update_phone_call_status(
                    mid, PhoneCallStatus.ENDED, ended_at=int(time()))
                self._active_calls.pop(mid, None)
        return callback

    def process_phone_call_requests(self):
        if not self._options.call_enabled:
            return

        db = self._store.phone_call_db
        statuses = PhoneCallStatus
        logger = self.logger

        for row in db.list(
                PhoneCallType.OUTGOING, self._own_number,
                status=statuses.CREATED, limit=10):
            mid = row['id']
            if not self._update_phone_call_status(
                    mid, statuses.DIALING, from_status=statuses.CREATED):
                continue
            try:
                call = self._modem.dial(
                    self.simplify_number(row['other_number']),
                    callStatusUpdateCallbackFunc=(
                        self._call_status_callback(mid)))
            except Exception as e:
                logger.error(f'phone call #{mid} failed due to {e!r}')
                self._update_phone_call_status(
                    mid, statuses.FAILED, ended_at=int(time()),
                    extra=dict(exc=repr(e), tb=format_tb(exc_info()[2])))
            else:
                self._active_calls[mid] = call

        for row in db.list(
                own_number=self._own_number,
                status=statuses.ANSWER_REQUESTED, limit=10):
            self._answer_phone_call(row['id'])

        for row in db.list(
                own_number=self._own_number,
                status=statuses.HANGUP_REQUESTED, limit=10):
            self._hangup_phone_call(row['id'])

    def _answer_phone_call(self, mid: int):
        statuses = PhoneCallStatus
        if not (call := self._active_calls.get(mid)):
            self._update_phone_call_status(
                mid, statuses.FAILED, ended_at=int(time()),
                extra=dict(error='live call is not available'))
            return
        try:
            call.answer()
        except Exception as e:
            self._update_phone_call_status(
                mid, statuses.FAILED, ended_at=int(time()),
                extra=dict(exc=repr(e), tb=format_tb(exc_info()[2])))
        else:
            self._update_phone_call_status(
                mid, statuses.ANSWERED, started_at=int(time()))

    def _hangup_phone_call(self, mid: int):
        statuses = PhoneCallStatus
        if not (call := self._active_calls.get(mid)):
            self._update_phone_call_status(
                mid, statuses.ENDED, ended_at=int(time()),
                extra=dict(error='live call is not available'))
            return
        try:
            call.hangup()
        except Exception as e:
            self._update_phone_call_status(
                mid, statuses.FAILED, ended_at=int(time()),
                extra=dict(exc=repr(e), tb=format_tb(exc_info()[2])))
        else:
            self._active_calls.pop(mid, None)
            self._update_phone_call_status(
                mid, statuses.ENDED, ended_at=int(time()))

    def _update_phone_call_status(
            self, mid: int, status: PhoneCallStatus, *,
            from_status: PhoneCallStatus | None = None,
            started_at=_EMPTY_ARG, ended_at=_EMPTY_ARG, extra=_EMPTY_ARG
                                  ) -> bool:
        before = self._store.get_phone_call(mid)
        kwargs = {}
        if started_at is not _EMPTY_ARG:
            kwargs['started_at'] = started_at
        if ended_at is not _EMPTY_ARG:
            kwargs['ended_at'] = ended_at
        if extra is not _EMPTY_ARG:
            kwargs['extra'] = extra
        if not self._store.phone_call_db.update_status(
                mid, status, from_status=from_status,
                **kwargs):
            return False

        after = self._store.get_phone_call(mid)
        if after and (before is None or before.status is not after.status):
            self._run_call_hook(mid, self._call_hook_name(after.status))
        return True

    @staticmethod
    def _call_hook_name(status: PhoneCallStatus) -> str:
        return {
            PhoneCallStatus.RINGING: 'received',
            PhoneCallStatus.DIALING: 'dialing',
            PhoneCallStatus.ANSWERED: 'answered',
            PhoneCallStatus.ENDED: 'ended',
            PhoneCallStatus.FAILED: 'failed',
        }.get(status, '')

    def _run_call_hook(self, mid: int, hook_name: str):
        if not hook_name:
            return
        cmd, configured_env = self._call_hook_config(hook_name)
        if not cmd:
            return
        event_time = int(time())
        hook_env = self._phone_call_hook_env(mid, event_time)
        hook_env.update({
            str(k): str(v) for k, v in (configured_env or {}).items()
        })
        run_system_command(
            cmd.format(**hook_env), env={**environ, **hook_env})

    def _call_hook_config(self, hook_name: str) -> tuple[str, dict | None]:
        options = self._options
        return (
            getattr(options, f'on_call_{hook_name}', ''),
            getattr(options, f'on_call_{hook_name}_env', None),
        )

    def _phone_call_hook_env(self, mid: int, event_time: int) -> dict[str, str]:
        call = self._store.get_phone_call(mid)
        audio = (AudioDeviceOptions.get(self._options.audio_device)
                 if self._options.audio_device else None)
        values = {
            'CALL_ID': mid,
            'CALL_DIRECTION': call.type.name if call else '',
            'CALL_OWN_NUMBER': call.own_number if call else self._own_number,
            'CALL_OTHER_NUMBER': call.other_number if call else '',
            'CALL_CALLER': call.caller if call else '',
            'CALL_RECIPIENT': call.recipient if call else '',
            'CALL_STATUS': call.status.name if call else '',
            'CALL_TIMESTAMP': event_time,
            'CALL_TIME_STR': timestamp_to_datetime(event_time),
            'CALL_STARTED_AT': int(call.started_at.timestamp())
            if call and call.started_at else '',
            'CALL_ENDED_AT': int(call.ended_at.timestamp())
            if call and call.ended_at else '',
            'CALL_AUDIO_DEVICE': audio.name if audio else '',
            'CALL_AUDIO_INPUT': audio.input if audio else '',
            'CALL_AUDIO_OUTPUT': audio.output if audio else '',
            'CALL_AUDIO_SAMPLE_RATE': audio.sample_rate if audio else '',
            'CALL_AUDIO_CHANNELS': audio.channels if audio else '',
            'CALL_AUDIO_FORMAT': audio.format if audio else '',
            'CALL_AUDIO_FRAME_MS': audio.frame_ms if audio else '',
        }
        return {k: str(v) for k, v in values.items()}

    def _handle_received_sms(self, sms: ReceivedSms):
        sender = self.normalise_number(sms.number)
        content = sms.text
        self.logger.info(
            f'received a new SMS from {sender!r}, length={len(content)}')
        recipient = self._own_number
        status = (ReceivedSMSStatus.READ
                  if sms.status == ReceivedSms.STATUS_RECEIVED_READ
                  else ReceivedSMSStatus.UNREAD)
        at = int(sms.time.timestamp())
        mid = self._store.add_received_sms(
            sender, content, status, at, self._extract_sms_part_info(sms))
        if mid is None:
            self.logger.info(
                f'received multipart SMS part from {sender!r}; awaiting more')
            return
        if stored_sms := self._store.get_received_sms(mid):
            content = stored_sms.content
            at = int(sms_t.timestamp()) if (sms_t := stored_sms.time) else at
        options = self._options
        if cmd := options.on_sms_received:
            run_system_command(cmd.format(
                SMS_SENDER=sender,
                SMS_RECIPIENT=recipient,
                SMS_CONTENT=content,
                SMS_TIMESTAMP=at,
                SMS_TIME_STR=timestamp_to_datetime(at)
            ), env=options.on_sms_received_env)

    def _extract_sms_part_info(self, sms: ReceivedSms
                               ) -> ReceivedSMSPartInfo | None:
        if udh := self._extract_sms_udh(sms):
            return udh

        attrs = _sms_attrs(sms)
        total = _first_int_attr(attrs, (
            'concat_total', 'concatTotal', 'total_parts', 'totalParts',
            'number_of_parts', 'numberOfParts'))
        sequence = _first_int_attr(attrs, (
            'concat_sequence', 'concatSequence', 'part_number', 'partNumber',
            'sequence'))
        reference = _first_attr(attrs, (
            'concat_reference', 'concatReference', 'multipart_reference',
            'multipartReference'))
        if reference is None or total is None or sequence is None:
            return None
        if total <= 1:
            return None
        return ReceivedSMSPartInfo(
            str(reference), total, sequence,
            _first_attr(attrs, ('pdu', 'raw_pdu', 'rawPdu')),
            _first_attr(attrs, ('encoding', 'smsEncoding')),
            {'source': 'attributes'})

    @classmethod
    def _extract_sms_udh(cls, sms: ReceivedSms) -> ReceivedSMSPartInfo | None:
        attrs = _sms_attrs(sms)
        udh = _first_attr(attrs, (
            'udh', 'user_data_header', 'userDataHeader',
            'userDataHeaderBytes'))
        if udh is None:
            return None
        if (concat := cls._parse_concat_udh(udh)) is None:
            return None
        reference, total, sequence = concat
        return ReceivedSMSPartInfo(
            reference, total, sequence,
            _first_attr(attrs, ('pdu', 'raw_pdu', 'rawPdu')),
            _first_attr(attrs, ('encoding', 'smsEncoding')),
            {'source': 'udh'})

    @staticmethod
    def _parse_concat_udh(udh) -> tuple[str, int, int] | None:
        data = _bytes_from_udh(udh)
        if not data:
            return None
        if len(data) >= 2 and data[0] == len(data) - 1:
            data = data[1:data[0] + 1]

        i = 0
        while i + 1 < len(data):
            iei = data[i]
            length = data[i + 1]
            value = data[i + 2:i + 2 + length]
            if len(value) != length:
                return None
            if iei == 0x00 and length == 3:
                return str(value[0]), value[1], value[2]
            if iei == 0x08 and length == 4:
                return str((value[0] << 8) | value[1]), value[2], value[3]
            i += 2 + length
        return None

    def _handle_status_report(self, report: StatusReport | ReceivedSms):
        self.logger.info(f'received a new status report {report}')

    def process_pending_smss(self):
        if not self._options.sms_enabled:
            return

        logger = self.logger
        process = self._store.pending_sms_db.process
        statuses = PendingSMSStatus
        send_sms = self.send_sms
        for sms in self._store.list_pending_smss(status=statuses.CREATED):
            p_mid = sms.id
            logger.info(f'processing pending SMS #{p_mid}...')
            if not process(p_mid, statuses.CREATED, statuses.PENDING):
                continue
            extra = None
            try:
                s_mid = send_sms(sms.recipient, sms.content)
            except Exception as e:
                logger.error(
                    f'could not process pending SMS #{p_mid} due to {e!r}')
                s_mid = None
                extra = dict(exc=repr(e), tb=format_tb(exc_info()[2]))
            else:
                logger.info(
                    f'pending SMS #{p_mid} is processed as sent SMS #{s_mid}')
            process(p_mid, statuses.PENDING, statuses.PROCESSED, s_mid, extra)

    def send_sms(self, recipient: str, content: str, *,
                 wait_for_delivery: bool | float = False) -> int | None:
        if not self._options.sms_enabled:
            raise RuntimeError(f'SMS sending is not enabled on this device')

        if self.check_network_coverage() <= 0:
            return None

        logger = self.logger
        recipient = self.normalise_number(recipient)
        sms_db = self._store.sms_db
        statuses = SentSMSStatus
        mid = sms_db.insert(
            SMSType.SENT, self._own_number, recipient, content,
            statuses.PENDING)
        if mid is None:
            raise RuntimeError('SMS could not be inserted into DB')

        logger.info(f'sending SMS #{mid} to {recipient!r}...')
        try:
            sms: SentSms = self._modem.sendSms(
                self.simplify_number(recipient), content,
                waitForDeliveryReport=bool(wait_for_delivery),
                deliveryTimeout=(10 if isinstance(wait_for_delivery, bool)
                                 else wait_for_delivery))
        except GSMTimeout:  # delivery timed out
            logger.error(f'SMS #{mid} was sent but delivery timed out')
            sms_db.update_status(mid, statuses.SENT)
        except Exception as e:
            logger.error(f'SMS #{mid} could not be sent due to {e!r}')
            sms_db.update_status(
                mid, statuses.FAILED,
                extra=dict(exc=repr(e), tb=format_tb(exc_info()[2])))
        else:
            report: StatusReport = sms.report
            extra = None
            log_method = 'info'
            if report is None:
                status = statuses.SENT
                msg = 'was sent but delivery status is unknown'
            elif (ds := report.deliveryStatus) is StatusReport.DELIVERED:
                status = statuses.DELIVERED
                msg = 'was sent and delivered'
            else:
                status = statuses.FAILED
                extra = dict(delivery_status=ds)
                msg = 'could not be sent'
                log_method = 'error'
            getattr(logger, log_method)(f'SMS #{mid} {msg}')
            sms_db.update_status(mid, status, extra=extra)

        return mid

    def read_sms(self, mid: int) -> StoredSMS | None:
        if (sms := self._store.get_received_sms(mid)) is None:
            raise ValueError(f'SMS #{mid} not found')
        if (status := sms.status) is ReceivedSMSStatus.UNREAD:
            self._store.sms_db.update_status(mid, ReceivedSMSStatus.READ)
        elif status is not ReceivedSMSStatus.READ:
            raise RuntimeError(
                f'cannot read SMS #{mid} for its status is {status!r}')
        return self._store.get_sms(mid)

    def mark_all_received_as_read(self) -> int:
        count = self._store.sms_db.batch_update_status(
            SMSType.RECEIVED, ReceivedSMSStatus.READ, ReceivedSMSStatus.UNREAD)
        self.logger.info(f'marked {count} received SMS(s) as read')
        return count

    def _loop(self, *,
              coverage_interval: int = 300,
              check_received_interval: int = 300):
        update_sim_status = safe(self._update_sim_card_status)
        process_pending = safe(self.process_pending_smss)
        process_call_requests = safe(self.process_phone_call_requests)
        check_coverage = safe(self.check_network_coverage)
        check_received = safe(self._check_modem_stored_smss)

        last_coverage_check = time()
        last_received_check = time()

        info = self.logger.info
        info(f'loop starting...')

        options = self._options
        awaiting = []
        if options.call_enabled:
            awaiting.append('calls')
        if options.sms_enabled:
            awaiting.append('SMSs')
        if awaiting:
            info(f'awaiting {" and ".join(awaiting)}...')

        count = 0
        while self._is_alive:
            if not count % 100:
                info(f'looping {count}/inf')
            update_sim_status()
            process_pending()
            process_call_requests()
            now = time()
            if now - last_coverage_check >= coverage_interval:
                last_coverage_check = now
                check_coverage()
            if now - last_received_check >= check_received_interval:
                last_received_check = now
                check_received()
            sleep(3)
            count += 1
        info('loop ended')

    def join(self):
        thread: Thread = self._loop_thread
        if thread is None or not thread.is_alive():
            return
        thread.join()

    def close(self):
        if not self._is_alive:
            return
        self.logger.info('closing...')
        self._is_alive = False
        self._loop_thread.join()
        self._modem.close()

    def restart(self):
        self.close()
        self._init()

    @classmethod
    def loop_all(cls):
        instances: list[cls] = []
        threads: dict[str, Thread] = {}
        stopped = False
        logger = cls.get_class_logger()

        def loop_one(_dev):
            instances.append(_c := cls(_dev))
            try:
                while not stopped:
                    sleep(.5)
            finally:
                _c.close()

        def new_thread(_d):
            logger.info(f'starting new thread for {_d}')
            threads[_d] = _t = Thread(target=loop_one, args=(_d,))
            _t.start()
            return _t

        def stop_all():
            logger.info('stopping all threads...')
            nonlocal stopped
            stopped = True
            for _t in threads.values():
                _t.join()
            logger.info('all threads are stopped')

        for d in config.get('DEVICES') or {}:
            new_thread(d)

        try:
            while True:
                sleep(60)
                for d, t in threads.items():
                    if t.is_alive():
                        continue
                    logger.warning(
                        f'thread for {d} is dead; recreating...')
                    new_thread(d)
        finally:
            stop_all()
