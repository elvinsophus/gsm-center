# -*- coding: utf-8 -*-

import json
import pytest
from enum import Enum

from app.db import (SIMCardDB, ContactDB, PendingSMSDB, SmsDB,
                    ReceivedSMSPartDB, PhoneCallDB, PhoneCallRecordingDB)

SENT = SmsDB.SMSType.SENT
RECEIVED = SmsDB.SMSType.RECEIVED
OUTGOING = PhoneCallDB.PhoneCallType.OUTGOING
INCOMING = PhoneCallDB.PhoneCallType.INCOMING
RECORDING = 'RECORDING'
OWN_NUMBER = '+12025550111'
OTHER_NUMBER = '+12025550122'
THIRD_NUMBER = '+12025550133'


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sim_db(fresh_db):
    return SIMCardDB()


@pytest.fixture
def contact_db(fresh_db):
    return ContactDB()


@pytest.fixture
def pending_db(fresh_db):
    return PendingSMSDB()


@pytest.fixture
def sms_db(fresh_db):
    return SmsDB()


@pytest.fixture
def received_sms_part_db(fresh_db):
    return ReceivedSMSPartDB()


@pytest.fixture
def phone_call_db(fresh_db):
    return PhoneCallDB()


@pytest.fixture
def phone_call_recording_db(fresh_db):
    return PhoneCallRecordingDB()


# ── SIMCardDB ─────────────────────────────────────────────────────────────────

class TestSIMCardDB:

    def test_insert_then_list(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        rows = sim_db.list()
        assert len(rows) == 1
        row = rows[0]
        assert row['gsm_port'] == '/dev/ttyUSB0'
        assert row['phone_number'] == '+8613500000001'
        assert row['call_enabled'] == 1
        assert row['sms_enabled'] == 1

    def test_update_existing_record(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        sim_db.update('/dev/ttyUSB0', '+8613500000001', False, False)
        rows = sim_db.list()
        assert len(rows) == 1
        assert rows[0]['call_enabled'] == 0
        assert rows[0]['sms_enabled'] == 0

    def test_multiple_devices(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        sim_db.update('/dev/ttyUSB1', '+8613500000002', False, True)
        assert len(sim_db.list()) == 2

    def test_filter_sms_enabled(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        sim_db.update('/dev/ttyUSB1', '+8613500000002', True, False)
        rows = sim_db.list(sms_enabled=True)
        assert len(rows) == 1
        assert rows[0]['phone_number'] == '+8613500000001'

    def test_filter_call_enabled(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        sim_db.update('/dev/ttyUSB1', '+8613500000002', False, True)
        rows = sim_db.list(call_enabled=False)
        assert len(rows) == 1
        assert rows[0]['phone_number'] == '+8613500000002'

    def test_filter_since(self, sim_db):
        import time
        before = int(time.time()) - 5
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        assert len(sim_db.list(since=before)) == 1
        assert len(sim_db.list(since=int(time.time()) + 60)) == 0

    def test_list_phone_numbers(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        sim_db.update('/dev/ttyUSB1', '+8613500000002', True, True)
        numbers = sim_db.list_phone_numbers()
        assert set(numbers) == {'+8613500000001', '+8613500000002'}

    def test_list_phone_numbers_filtered(self, sim_db):
        sim_db.update('/dev/ttyUSB0', '+8613500000001', True, True)
        sim_db.update('/dev/ttyUSB1', '+8613500000002', True, False)
        numbers = sim_db.list_phone_numbers(sms_enabled=True)
        assert numbers == ['+8613500000001']


# ── PendingSMSDB ──────────────────────────────────────────────────────────────

class TestContactDB:

    def test_upsert_and_list(self, contact_db):
        contact_db.upsert('Alice', OTHER_NUMBER)

        rows = contact_db.list()

        assert len(rows) == 1
        assert rows[0]['alias'] == 'Alice'
        assert rows[0]['phone_number'] == OTHER_NUMBER

    def test_alias_lookup_is_case_insensitive(self, contact_db):
        contact_db.upsert('Alice', OTHER_NUMBER)

        row = contact_db.get_by_alias('alice')

        assert row['phone_number'] == OTHER_NUMBER

    def test_delete_by_alias_is_case_insensitive(self, contact_db):
        contact_db.upsert('Alice', OTHER_NUMBER)

        assert contact_db.delete_by_alias('alice') is True
        assert contact_db.list() == []


class TestPendingSMSDB:

    def test_insert_and_get(self, pending_db):
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hello', 'CREATED')
        row = pending_db.get(mid)
        assert row is not None
        assert row['sender'] == OWN_NUMBER
        assert row['recipient'] == OTHER_NUMBER
        assert row['content'] == 'hello'
        assert row['status'] == 'CREATED'
        assert row['sent_sms_id'] is None

    def test_insert_with_enum_status(self, pending_db):
        class S(Enum):
            CREATED = 0
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hi', S.CREATED)
        assert pending_db.get(mid)['status'] == 'CREATED'

    def test_get_nonexistent_returns_none(self, pending_db):
        assert pending_db.get(9999) is None

    def test_list_by_sender(self, pending_db):
        pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'a', 'CREATED')
        pending_db.insert(THIRD_NUMBER, OTHER_NUMBER, 'b', 'CREATED')
        rows = pending_db.list(OWN_NUMBER)
        assert len(rows) == 1
        assert rows[0]['content'] == 'a'

    def test_list_filter_by_status(self, pending_db):
        pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'a', 'CREATED')
        pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'b', 'PENDING')
        assert len(pending_db.list(OWN_NUMBER, status='CREATED')) == 1
        assert len(pending_db.list(OWN_NUMBER, status='PENDING')) == 1

    def test_list_limit(self, pending_db):
        for i in range(5):
            pending_db.insert(OWN_NUMBER, OTHER_NUMBER, f'msg{i}', 'CREATED')
        assert len(pending_db.list(OWN_NUMBER, limit=3)) == 3

    def test_process_advances_status(self, pending_db):
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hi', 'CREATED')
        result = pending_db.process(mid, 'CREATED', 'PENDING')
        assert result is not None
        assert result['status'] == 'PENDING'

    def test_process_wrong_from_status_returns_none(self, pending_db):
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hi', 'CREATED')
        result = pending_db.process(mid, 'PENDING', 'PROCESSED')
        assert result is None
        assert pending_db.get(mid)['status'] == 'CREATED'

    def test_process_sets_sent_sms_id(self, pending_db):
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hi', 'CREATED')
        pending_db.process(mid, 'CREATED', 'PENDING', sent_sms_id=42)
        assert pending_db.get(mid)['sent_sms_id'] == 42

    def test_process_with_enum_statuses(self, pending_db):
        class S(Enum):
            CREATED = 0
            PENDING = 1
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hi', 'CREATED')
        result = pending_db.process(mid, S.CREATED, S.PENDING)
        assert result['status'] == 'PENDING'

    def test_delete(self, pending_db):
        mid = pending_db.insert(OWN_NUMBER, OTHER_NUMBER, 'hi', 'CREATED')
        assert pending_db.delete(mid) is True
        assert pending_db.get(mid) is None

    def test_delete_nonexistent_returns_false(self, pending_db):
        assert pending_db.delete(9999) is False


# ── SmsDB ─────────────────────────────────────────────────────────────────────

class TestSmsDB:

    def test_insert_and_get(self, sms_db):
        mid = sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'hello', 'PENDING')
        row = sms_db.get(mid)
        assert row is not None
        assert row['type'] == 'SENT'
        assert row['own_number'] == OWN_NUMBER
        assert row['other_number'] == OTHER_NUMBER
        assert row['content'] == 'hello'
        assert row['status'] == 'PENDING'
        assert row['delivery_report'] is None

    def test_insert_with_enum_type_and_status(self, sms_db):
        mid = sms_db.insert(RECEIVED, OWN_NUMBER, THIRD_NUMBER, 'hi', 'UNREAD')
        assert sms_db.get(mid)['type'] == 'RECEIVED'
        assert sms_db.get(mid)['status'] == 'UNREAD'

    def test_insert_with_timestamp(self, sms_db):
        mid = sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'hi', 'UNREAD', time_=1700000000)
        assert sms_db.get(mid)['time'] == 1700000000

    def test_get_nonexistent_returns_none(self, sms_db):
        assert sms_db.get(9999) is None

    def test_list_by_type(self, sms_db):
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'sent', 'SENT')
        sms_db.insert(RECEIVED, OWN_NUMBER, THIRD_NUMBER, 'rcvd', 'UNREAD')
        rows = sms_db.list(SENT, OWN_NUMBER)
        assert len(rows) == 1
        assert rows[0]['type'] == 'SENT'

    def test_list_all_types(self, sms_db):
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'a', 'SENT')
        sms_db.insert(RECEIVED, OWN_NUMBER, THIRD_NUMBER, 'b', 'UNREAD')
        assert len(sms_db.list(own_number=OWN_NUMBER)) == 2

    def test_list_by_other_number(self, sms_db):
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'a', 'SENT')
        sms_db.insert(SENT, OWN_NUMBER, THIRD_NUMBER, 'b', 'SENT')
        rows = sms_db.list(SENT, OWN_NUMBER, other_number=OTHER_NUMBER)
        assert len(rows) == 1
        assert rows[0]['content'] == 'a'

    def test_list_by_status(self, sms_db):
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'a', 'SENT')
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'b', 'FAILED')
        rows = sms_db.list(SENT, OWN_NUMBER, status='FAILED')
        assert len(rows) == 1
        assert rows[0]['content'] == 'b'

    def test_list_status_requires_type(self, sms_db):
        with pytest.raises(ValueError, match='`type_`'):
            sms_db.list(status='SENT')

    def test_list_other_number_requires_own_number(self, sms_db):
        with pytest.raises(ValueError, match='`own_number`'):
            sms_db.list(other_number=OTHER_NUMBER)

    def test_list_limit(self, sms_db):
        for i in range(5):
            sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, f'msg{i}', 'SENT')
        assert len(sms_db.list(SENT, OWN_NUMBER, limit=3)) == 3

    def test_list_ordered_newest_first(self, sms_db):
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'first', 'SENT')
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'second', 'SENT')
        rows = sms_db.list(SENT, OWN_NUMBER)
        assert rows[0]['content'] == 'second'

    def test_update_status(self, sms_db):
        mid = sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'hi', 'PENDING')
        assert sms_db.update_status(mid, 'SENT') is True
        assert sms_db.get(mid)['status'] == 'SENT'

    def test_update_status_nonexistent_returns_false(self, sms_db):
        assert sms_db.update_status(9999, 'SENT') is False

    def test_update_status_sets_delivery_report(self, sms_db):
        mid = sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'hi', 'PENDING')
        sms_db.update_status(mid, 'DELIVERED', delivery_report={'code': 0})
        row = sms_db.get(mid)
        assert json.loads(row['delivery_report']) == {'code': 0}

    def test_update_status_delivery_report_none_stored(self, sms_db):
        mid = sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'hi', 'PENDING')
        sms_db.update_status(mid, 'SENT', delivery_report=None)
        assert sms_db.get(mid)['delivery_report'] is None

    def test_update_status_without_delivery_report_leaves_it_unchanged(self, sms_db):
        mid = sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'hi', 'PENDING')
        sms_db.update_status(mid, 'SENT')
        assert sms_db.get(mid)['delivery_report'] is None

    def test_batch_update_status(self, sms_db):
        sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'a', 'UNREAD')
        sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'b', 'UNREAD')
        count = sms_db.batch_update_status(RECEIVED, 'READ', 'UNREAD')
        assert count == 2
        assert all(r['status'] == 'READ'
                   for r in sms_db.list(RECEIVED, OWN_NUMBER))

    def test_batch_update_status_respects_from_status(self, sms_db):
        sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'a', 'UNREAD')
        sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'b', 'READ')
        count = sms_db.batch_update_status(RECEIVED, 'READ', 'UNREAD')
        assert count == 1

    def test_batch_update_without_from_status(self, sms_db):
        sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'a', 'UNREAD')
        sms_db.insert(RECEIVED, OWN_NUMBER, OTHER_NUMBER, 'b', 'READ')
        count = sms_db.batch_update_status(RECEIVED, 'READ')
        assert count == 2

    def test_list_last_of_each_returns_latest_per_conversation(self, sms_db):
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'first', 'SENT')
        sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'second', 'SENT')
        sms_db.insert(RECEIVED, OWN_NUMBER, THIRD_NUMBER, 'hi', 'UNREAD')
        rows = sms_db.list_last_of_each(OWN_NUMBER)
        assert len(rows) == 2
        conv_2222 = next(r for r in rows if r['other_number'] == OTHER_NUMBER)
        assert conv_2222['content'] == 'second'
        assert conv_2222['id_count'] == 2

    def test_delete(self, sms_db):
        mid = sms_db.insert(SENT, OWN_NUMBER, OTHER_NUMBER, 'hi', 'SENT')
        assert sms_db.delete(mid) is True
        assert sms_db.get(mid) is None

    def test_delete_nonexistent_returns_false(self, sms_db):
        assert sms_db.delete(9999) is False


class TestReceivedSMSPartDB:

    def test_insert_and_get_by_key(self, received_sms_part_db):
        mid = received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello ', 'abc', 2, 1, 'RECEIVED',
            time_=1700000000, raw_pdu='00', encoding='GSM7',
            extra={'source': 'test'})

        row = received_sms_part_db.get_by_key(OWN_NUMBER, OTHER_NUMBER, 'abc', 1)
        assert row['id'] == mid
        assert row['content'] == 'hello '
        assert row['concat_total'] == 2
        assert row['concat_sequence'] == 1
        assert row['time'] == 1700000000
        assert row['raw_pdu'] == '00'
        assert row['encoding'] == 'GSM7'
        assert row['status'] == 'RECEIVED'
        assert json.loads(row['extra']) == {'source': 'test'}

    def test_insert_duplicate_is_idempotent(self, received_sms_part_db):
        first = received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello ', 'abc', 2, 1, 'RECEIVED')
        second = received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello again ', 'abc', 2, 1, 'RECEIVED')

        rows = received_sms_part_db.list_group(OWN_NUMBER, OTHER_NUMBER, 'abc')
        assert first == second
        assert len(rows) == 1
        assert rows[0]['content'] == 'hello '

    def test_list_group_orders_by_sequence(self, received_sms_part_db):
        received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'world', 'abc', 2, 2, 'RECEIVED')
        received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello ', 'abc', 2, 1, 'RECEIVED')

        rows = received_sms_part_db.list_group(OWN_NUMBER, OTHER_NUMBER, 'abc')

        assert [r['concat_sequence'] for r in rows] == [1, 2]

    def test_mark_group_assembled(self, received_sms_part_db):
        received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello ', 'abc', 2, 1, 'RECEIVED')
        received_sms_part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'world', 'abc', 2, 2, 'RECEIVED')

        count = received_sms_part_db.mark_group_assembled(
            OWN_NUMBER, OTHER_NUMBER, 'abc', 42, 'ASSEMBLED')

        rows = received_sms_part_db.list_group(OWN_NUMBER, OTHER_NUMBER, 'abc')
        assert count == 2
        assert all(r['sms_id'] == 42 for r in rows)
        assert all(r['status'] == 'ASSEMBLED' for r in rows)


class TestPhoneCallDB:

    def test_insert_and_get(self, phone_call_db):
        mid = phone_call_db.insert(OUTGOING, OWN_NUMBER, OTHER_NUMBER, 'CREATED')
        row = phone_call_db.get(mid)
        assert row is not None
        assert row['type'] == 'OUTGOING'
        assert row['own_number'] == OWN_NUMBER
        assert row['other_number'] == OTHER_NUMBER
        assert row['status'] == 'CREATED'
        assert row['started_at'] is None
        assert row['ended_at'] is None

    def test_insert_with_enum_status(self, phone_call_db):
        class S(Enum):
            RINGING = 0
        mid = phone_call_db.insert(INCOMING, OWN_NUMBER, OTHER_NUMBER, S.RINGING)
        assert phone_call_db.get(mid)['status'] == 'RINGING'

    def test_list_by_own_number_and_status(self, phone_call_db):
        phone_call_db.insert(OUTGOING, OWN_NUMBER, OTHER_NUMBER, 'CREATED')
        phone_call_db.insert(INCOMING, OWN_NUMBER, THIRD_NUMBER, 'RINGING')
        rows = phone_call_db.list(own_number=OWN_NUMBER, status='RINGING')
        assert len(rows) == 1
        assert rows[0]['other_number'] == THIRD_NUMBER

    def test_update_status_from_status(self, phone_call_db):
        mid = phone_call_db.insert(INCOMING, OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        assert phone_call_db.update_status(
            mid, 'ANSWER_REQUESTED', from_status='RINGING') is True
        assert phone_call_db.get(mid)['status'] == 'ANSWER_REQUESTED'

    def test_update_status_wrong_from_status_returns_false(self, phone_call_db):
        mid = phone_call_db.insert(INCOMING, OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        assert phone_call_db.update_status(
            mid, 'ANSWER_REQUESTED', from_status='ENDED') is False
        assert phone_call_db.get(mid)['status'] == 'RINGING'

    def test_update_status_sets_times_and_extra(self, phone_call_db):
        mid = phone_call_db.insert(OUTGOING, OWN_NUMBER, OTHER_NUMBER, 'DIALING')
        phone_call_db.update_status(
            mid, 'FAILED', started_at=1700000000, ended_at=1700000060,
            extra={'reason': 'busy'})
        row = phone_call_db.get(mid)
        assert row['started_at'] == 1700000000
        assert row['ended_at'] == 1700000060
        assert json.loads(row['extra']) == {'reason': 'busy'}


class TestPhoneCallRecordingDB:

    def test_insert_and_get(self, phone_call_recording_db):
        mid = phone_call_recording_db.insert(
            42, 'recordings/call.wav', 'wav', RECORDING,
            started_at=1700000000, extra={'pid': 123})

        row = phone_call_recording_db.get(mid)

        assert row['call_id'] == 42
        assert row['path'] == 'recordings/call.wav'
        assert row['format'] == 'wav'
        assert row['status'] == RECORDING
        assert row['started_at'] == 1700000000
        assert json.loads(row['extra']) == {'pid': 123}

    def test_list_by_call(self, phone_call_recording_db):
        phone_call_recording_db.insert(1, 'a.wav', 'wav', RECORDING)
        phone_call_recording_db.insert(2, 'b.wav', 'wav', RECORDING)

        rows = phone_call_recording_db.list(1)

        assert len(rows) == 1
        assert rows[0]['path'] == 'a.wav'

    def test_update_status(self, phone_call_recording_db):
        mid = phone_call_recording_db.insert(1, 'a.wav', 'wav', RECORDING)

        assert phone_call_recording_db.update_status(
            mid, 'COMPLETED', ended_at=1700000060,
            extra={'return_code': 0}) is True

        row = phone_call_recording_db.get(mid)
        assert row['status'] == 'COMPLETED'
        assert row['ended_at'] == 1700000060
        assert json.loads(row['extra']) == {'return_code': 0}
