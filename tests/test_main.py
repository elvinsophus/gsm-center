# -*- coding: utf-8 -*-

from unittest.mock import Mock

from app.main import GSMCenter, GSMStore


class TestPhoneCallRequests:

    def test_hangup_request_rejects_finished_call(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', '+1111', '+2222', 'ENDED')

        assert GSMStore.request_phone_call_hangup(mid) is False
        assert db.get(mid)['status'] == 'ENDED'

    def test_hangup_request_is_idempotent(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', '+1111', '+2222', 'HANGUP_REQUESTED')

        assert GSMStore.request_phone_call_hangup(mid) is True
        assert db.get(mid)['status'] == 'HANGUP_REQUESTED'


class TestPhoneCallStartupCleanup:

    def test_clear_stale_phone_calls_marks_in_flight_calls_ended(
            self, fresh_db):
        db = GSMStore.phone_call_db
        stale_id = db.insert('INCOMING', '+1111', '+2222', 'RINGING')
        finished_id = db.insert('INCOMING', '+1111', '+3333', 'ENDED')

        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._own_number = '+1111'
        center._store = GSMStore('+1111')
        center.logger = Mock()

        center._clear_stale_phone_calls()

        stale = db.get(stale_id)
        finished = db.get(finished_id)
        assert stale['status'] == 'ENDED'
        assert stale['ended_at'] is not None
        assert 'loop restarted' in stale['extra']
        assert finished['status'] == 'ENDED'
