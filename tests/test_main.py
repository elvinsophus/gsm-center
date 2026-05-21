# -*- coding: utf-8 -*-

from unittest.mock import Mock, patch

from app.main import (GSMCenter, GSMStore, ReceivedSMSPartInfo,
                      ReceivedSMSPartStatus, ReceivedSMSStatus)

OWN_NUMBER = '+12025550111'
OTHER_NUMBER = '+12025550122'
THIRD_NUMBER = '+12025550133'


class TestPhoneCallRequests:

    def test_hangup_request_rejects_finished_call(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ENDED')

        assert GSMStore.request_phone_call_hangup(mid) is False
        assert db.get(mid)['status'] == 'ENDED'

    def test_hangup_request_is_idempotent(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'HANGUP_REQUESTED')

        assert GSMStore.request_phone_call_hangup(mid) is True
        assert db.get(mid)['status'] == 'HANGUP_REQUESTED'


class TestPhoneCallStartupCleanup:

    def test_clear_stale_phone_calls_marks_in_flight_calls_ended(
            self, fresh_db):
        db = GSMStore.phone_call_db
        stale_id = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        finished_id = db.insert('INCOMING', OWN_NUMBER, THIRD_NUMBER, 'ENDED')

        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center.logger = Mock()

        center._clear_stale_phone_calls()

        stale = db.get(stale_id)
        finished = db.get(finished_id)
        assert stale['status'] == 'ENDED'
        assert stale['ended_at'] is not None
        assert 'loop restarted' in stale['extra']
        assert finished['status'] == 'ENDED'


class TestPhoneCallHooks:

    def make_center(self):
        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(
            call_enabled=True,
            audio_device='gsm_usb',
            on_call_answered='./answered {CALL_ID} {CALL_STATUS}',
            on_call_answered_env={'CUSTOM': 'yes'})
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center.logger = Mock()
        return center

    def test_status_transition_runs_matching_hook(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        audio = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)

        with patch('app.main.AudioDeviceOptions.get', return_value=audio), \
                patch('app.main.run_system_command') as run:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED, started_at=1700000000)

        assert run.call_count == 1
        command = run.call_args.args[0]
        env = run.call_args.kwargs['env']
        assert command == f'./answered {mid} ANSWERED'
        assert env['CALL_ID'] == str(mid)
        assert env['CALL_DIRECTION'] == 'INCOMING'
        assert env['CALL_OWN_NUMBER'] == OWN_NUMBER
        assert env['CALL_OTHER_NUMBER'] == OTHER_NUMBER
        assert env['CALL_CALLER'] == OTHER_NUMBER
        assert env['CALL_RECIPIENT'] == OWN_NUMBER
        assert env['CALL_STATUS'] == 'ANSWERED'
        assert env['CALL_STARTED_AT'] == '1700000000'
        assert env['CALL_AUDIO_DEVICE'] == 'gsm_usb'
        assert env['CALL_AUDIO_INPUT'] == 'plughw:3,0'
        assert env['CUSTOM'] == 'yes'

    def test_same_status_update_does_not_rerun_hook(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')

        with patch('app.main.run_system_command') as run:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED)

        run.assert_not_called()


class TestMultipartSMS:

    def test_add_received_sms_waits_for_missing_parts(self, fresh_db):
        store = GSMStore(OWN_NUMBER)

        mid = store.add_received_sms(
            OTHER_NUMBER, 'world', ReceivedSMSStatus.UNREAD, 1700000001,
            ReceivedSMSPartInfo('abc', 2, 2))

        assert mid is None
        assert store.list_received_smss(sender=OTHER_NUMBER) == []

    def test_add_received_sms_assembles_out_of_order_parts(self, fresh_db):
        store = GSMStore(OWN_NUMBER)
        store.add_received_sms(
            OTHER_NUMBER, 'world', ReceivedSMSStatus.UNREAD, 1700000001,
            ReceivedSMSPartInfo('abc', 2, 2))

        mid = store.add_received_sms(
            OTHER_NUMBER, 'hello ', ReceivedSMSStatus.UNREAD, 1700000000,
            ReceivedSMSPartInfo('abc', 2, 1))

        sms = store.get_received_sms(mid)
        parts = GSMStore.received_sms_part_db.list_group(
            OWN_NUMBER, OTHER_NUMBER, 'abc')
        assert sms.content == 'hello world'
        assert sms.status is ReceivedSMSStatus.UNREAD
        assert all(
            p['status'] == ReceivedSMSPartStatus.ASSEMBLED.name
            for p in parts)
        assert all(p['sms_id'] == mid for p in parts)

    def test_assemble_all_received_sms_parts_handles_restart_state(
            self, fresh_db):
        store = GSMStore(OWN_NUMBER)
        part_db = GSMStore.received_sms_part_db
        part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello ', 'abc', 2, 1,
            ReceivedSMSPartStatus.RECEIVED, time_=1700000000)
        part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'world', 'abc', 2, 2,
            ReceivedSMSPartStatus.RECEIVED, time_=1700000001)

        count = store.assemble_all_received_sms_parts()

        messages = store.list_received_smss(sender=OTHER_NUMBER)
        assert count == 1
        assert len(messages) == 1
        assert messages[0].content == 'hello world'
        assert int(messages[0].time.timestamp()) == 1700000000

    def test_parse_8_bit_concat_udh(self):
        assert GSMCenter._parse_concat_udh(bytes.fromhex('0500032a0201')) == (
            '42', 2, 1)

    def test_parse_8_bit_concat_udh_without_length_prefix(self):
        assert GSMCenter._parse_concat_udh(bytes.fromhex('00032a0201')) == (
            '42', 2, 1)

    def test_parse_16_bit_concat_udh(self):
        assert GSMCenter._parse_concat_udh(bytes.fromhex('06080401020302')) == (
            '258', 3, 2)

    def test_received_hook_uses_integer_timestamp_for_assembled_sms(
            self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._options = GSMCenter.DeviceOptions(
            sms_enabled=True,
            on_sms_received='./sms {SMS_CONTENT} {SMS_TIMESTAMP}',
        )
        center.logger = Mock()

        first = Mock()
        first.number = OTHER_NUMBER
        first.text = 'hello '
        first.status = object()
        first.time.timestamp.return_value = 1700000000
        first.concat_reference = 'abc'
        first.concat_total = 2
        first.concat_sequence = 1

        second = Mock()
        second.number = OTHER_NUMBER
        second.text = 'world'
        second.status = object()
        second.time.timestamp.return_value = 1700000001
        second.concat_reference = 'abc'
        second.concat_total = 2
        second.concat_sequence = 2

        with patch('app.main.run_system_command') as run:
            center._handle_received_sms(first)
            center._handle_received_sms(second)

        run.assert_called_once()
        command = run.call_args.args[0]
        assert command == './sms hello world 1700000000'
