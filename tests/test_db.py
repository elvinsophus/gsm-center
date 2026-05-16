# -*- coding: utf-8 -*-

import json
import pytest
from enum import Enum

from app.db import SIMCardDB, PendingSMSDB, SmsDB

SENT = SmsDB.SMSType.SENT
RECEIVED = SmsDB.SMSType.RECEIVED


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sim_db(fresh_db):
    return SIMCardDB()


@pytest.fixture
def pending_db(fresh_db):
    return PendingSMSDB()


@pytest.fixture
def sms_db(fresh_db):
    return SmsDB()


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

class TestPendingSMSDB:

    def test_insert_and_get(self, pending_db):
        mid = pending_db.insert('+1111', '+2222', 'hello', 'CREATED')
        row = pending_db.get(mid)
        assert row is not None
        assert row['sender'] == '+1111'
        assert row['recipient'] == '+2222'
        assert row['content'] == 'hello'
        assert row['status'] == 'CREATED'
        assert row['sent_sms_id'] is None

    def test_insert_with_enum_status(self, pending_db):
        class S(Enum):
            CREATED = 0
        mid = pending_db.insert('+1111', '+2222', 'hi', S.CREATED)
        assert pending_db.get(mid)['status'] == 'CREATED'

    def test_get_nonexistent_returns_none(self, pending_db):
        assert pending_db.get(9999) is None

    def test_list_by_sender(self, pending_db):
        pending_db.insert('+1111', '+2222', 'a', 'CREATED')
        pending_db.insert('+3333', '+2222', 'b', 'CREATED')
        rows = pending_db.list('+1111')
        assert len(rows) == 1
        assert rows[0]['content'] == 'a'

    def test_list_filter_by_status(self, pending_db):
        pending_db.insert('+1111', '+2222', 'a', 'CREATED')
        pending_db.insert('+1111', '+2222', 'b', 'PENDING')
        assert len(pending_db.list('+1111', status='CREATED')) == 1
        assert len(pending_db.list('+1111', status='PENDING')) == 1

    def test_list_limit(self, pending_db):
        for i in range(5):
            pending_db.insert('+1111', '+2222', f'msg{i}', 'CREATED')
        assert len(pending_db.list('+1111', limit=3)) == 3

    def test_process_advances_status(self, pending_db):
        mid = pending_db.insert('+1111', '+2222', 'hi', 'CREATED')
        result = pending_db.process(mid, 'CREATED', 'PENDING')
        assert result is not None
        assert result['status'] == 'PENDING'

    def test_process_wrong_from_status_returns_none(self, pending_db):
        mid = pending_db.insert('+1111', '+2222', 'hi', 'CREATED')
        result = pending_db.process(mid, 'PENDING', 'PROCESSED')
        assert result is None
        assert pending_db.get(mid)['status'] == 'CREATED'

    def test_process_sets_sent_sms_id(self, pending_db):
        mid = pending_db.insert('+1111', '+2222', 'hi', 'CREATED')
        pending_db.process(mid, 'CREATED', 'PENDING', sent_sms_id=42)
        assert pending_db.get(mid)['sent_sms_id'] == 42

    def test_process_with_enum_statuses(self, pending_db):
        class S(Enum):
            CREATED = 0
            PENDING = 1
        mid = pending_db.insert('+1111', '+2222', 'hi', 'CREATED')
        result = pending_db.process(mid, S.CREATED, S.PENDING)
        assert result['status'] == 'PENDING'

    def test_delete(self, pending_db):
        mid = pending_db.insert('+1111', '+2222', 'hi', 'CREATED')
        assert pending_db.delete(mid) is True
        assert pending_db.get(mid) is None

    def test_delete_nonexistent_returns_false(self, pending_db):
        assert pending_db.delete(9999) is False


# ── SmsDB ─────────────────────────────────────────────────────────────────────

class TestSmsDB:

    def test_insert_and_get(self, sms_db):
        mid = sms_db.insert(SENT, '+1111', '+2222', 'hello', 'PENDING')
        row = sms_db.get(mid)
        assert row is not None
        assert row['type'] == 'SENT'
        assert row['own_number'] == '+1111'
        assert row['other_number'] == '+2222'
        assert row['content'] == 'hello'
        assert row['status'] == 'PENDING'
        assert row['delivery_report'] is None

    def test_insert_with_enum_type_and_status(self, sms_db):
        mid = sms_db.insert(RECEIVED, '+1111', '+3333', 'hi', 'UNREAD')
        assert sms_db.get(mid)['type'] == 'RECEIVED'
        assert sms_db.get(mid)['status'] == 'UNREAD'

    def test_insert_with_timestamp(self, sms_db):
        mid = sms_db.insert(RECEIVED, '+1111', '+2222', 'hi', 'UNREAD', time_=1700000000)
        assert sms_db.get(mid)['time'] == 1700000000

    def test_get_nonexistent_returns_none(self, sms_db):
        assert sms_db.get(9999) is None

    def test_list_by_type(self, sms_db):
        sms_db.insert(SENT, '+1111', '+2222', 'sent', 'SENT')
        sms_db.insert(RECEIVED, '+1111', '+3333', 'rcvd', 'UNREAD')
        rows = sms_db.list(SENT, '+1111')
        assert len(rows) == 1
        assert rows[0]['type'] == 'SENT'

    def test_list_all_types(self, sms_db):
        sms_db.insert(SENT, '+1111', '+2222', 'a', 'SENT')
        sms_db.insert(RECEIVED, '+1111', '+3333', 'b', 'UNREAD')
        assert len(sms_db.list(own_number='+1111')) == 2

    def test_list_by_other_number(self, sms_db):
        sms_db.insert(SENT, '+1111', '+2222', 'a', 'SENT')
        sms_db.insert(SENT, '+1111', '+3333', 'b', 'SENT')
        rows = sms_db.list(SENT, '+1111', other_number='+2222')
        assert len(rows) == 1
        assert rows[0]['content'] == 'a'

    def test_list_by_status(self, sms_db):
        sms_db.insert(SENT, '+1111', '+2222', 'a', 'SENT')
        sms_db.insert(SENT, '+1111', '+2222', 'b', 'FAILED')
        rows = sms_db.list(SENT, '+1111', status='FAILED')
        assert len(rows) == 1
        assert rows[0]['content'] == 'b'

    def test_list_status_requires_type(self, sms_db):
        with pytest.raises(ValueError, match='`type_`'):
            sms_db.list(status='SENT')

    def test_list_other_number_requires_own_number(self, sms_db):
        with pytest.raises(ValueError, match='`own_number`'):
            sms_db.list(other_number='+2222')

    def test_list_limit(self, sms_db):
        for i in range(5):
            sms_db.insert(SENT, '+1111', '+2222', f'msg{i}', 'SENT')
        assert len(sms_db.list(SENT, '+1111', limit=3)) == 3

    def test_list_ordered_newest_first(self, sms_db):
        sms_db.insert(SENT, '+1111', '+2222', 'first', 'SENT')
        sms_db.insert(SENT, '+1111', '+2222', 'second', 'SENT')
        rows = sms_db.list(SENT, '+1111')
        assert rows[0]['content'] == 'second'

    def test_update_status(self, sms_db):
        mid = sms_db.insert(SENT, '+1111', '+2222', 'hi', 'PENDING')
        assert sms_db.update_status(mid, 'SENT') is True
        assert sms_db.get(mid)['status'] == 'SENT'

    def test_update_status_nonexistent_returns_false(self, sms_db):
        assert sms_db.update_status(9999, 'SENT') is False

    def test_update_status_sets_delivery_report(self, sms_db):
        mid = sms_db.insert(SENT, '+1111', '+2222', 'hi', 'PENDING')
        sms_db.update_status(mid, 'DELIVERED', delivery_report={'code': 0})
        row = sms_db.get(mid)
        assert json.loads(row['delivery_report']) == {'code': 0}

    def test_update_status_delivery_report_none_stored(self, sms_db):
        mid = sms_db.insert(SENT, '+1111', '+2222', 'hi', 'PENDING')
        sms_db.update_status(mid, 'SENT', delivery_report=None)
        assert sms_db.get(mid)['delivery_report'] is None

    def test_update_status_without_delivery_report_leaves_it_unchanged(self, sms_db):
        mid = sms_db.insert(SENT, '+1111', '+2222', 'hi', 'PENDING')
        sms_db.update_status(mid, 'SENT')
        assert sms_db.get(mid)['delivery_report'] is None

    def test_batch_update_status(self, sms_db):
        sms_db.insert(RECEIVED, '+1111', '+2222', 'a', 'UNREAD')
        sms_db.insert(RECEIVED, '+1111', '+2222', 'b', 'UNREAD')
        count = sms_db.batch_update_status(RECEIVED, 'READ', 'UNREAD')
        assert count == 2
        assert all(r['status'] == 'READ'
                   for r in sms_db.list(RECEIVED, '+1111'))

    def test_batch_update_status_respects_from_status(self, sms_db):
        sms_db.insert(RECEIVED, '+1111', '+2222', 'a', 'UNREAD')
        sms_db.insert(RECEIVED, '+1111', '+2222', 'b', 'READ')
        count = sms_db.batch_update_status(RECEIVED, 'READ', 'UNREAD')
        assert count == 1

    def test_batch_update_without_from_status(self, sms_db):
        sms_db.insert(RECEIVED, '+1111', '+2222', 'a', 'UNREAD')
        sms_db.insert(RECEIVED, '+1111', '+2222', 'b', 'READ')
        count = sms_db.batch_update_status(RECEIVED, 'READ')
        assert count == 2

    def test_list_last_of_each_returns_latest_per_conversation(self, sms_db):
        sms_db.insert(SENT, '+1111', '+2222', 'first', 'SENT')
        sms_db.insert(SENT, '+1111', '+2222', 'second', 'SENT')
        sms_db.insert(RECEIVED, '+1111', '+3333', 'hi', 'UNREAD')
        rows = sms_db.list_last_of_each('+1111')
        assert len(rows) == 2
        conv_2222 = next(r for r in rows if r['other_number'] == '+2222')
        assert conv_2222['content'] == 'second'
        assert conv_2222['id_count'] == 2

    def test_delete(self, sms_db):
        mid = sms_db.insert(SENT, '+1111', '+2222', 'hi', 'SENT')
        assert sms_db.delete(mid) is True
        assert sms_db.get(mid) is None

    def test_delete_nonexistent_returns_false(self, sms_db):
        assert sms_db.delete(9999) is False
